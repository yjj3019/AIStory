#!/usr/bin/env python3
"""느린 클립을 속도 값을 조정해 정상 자/초(6.2~7.0)로 재합성한다."""
import json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "audio18"
VOICE = "avocado_v2:qvd_04433"
items = {it["id"]: it for it in json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))["items"]}
TARGET = 6.6


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                 "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout.strip())


def render_at(it, speed, mp3):
    raw = mp3.with_suffix(".raw.mp3")
    r = subprocess.run(["/opt/hatch/bin/tts", "speak", "--voice", VOICE,
                        "--language", "ko", "--speed", str(speed),
                        "--output", str(raw), "--text-stdin"],
                       input=it["text"], capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not raw.exists():
        print("FAIL", it["id"], (r.stdout + r.stderr)[-200:], flush=True)
        return None
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                    "-af", "loudnorm=I=-24.4:TP=-2.0:LRA=11",
                    "-codec:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(mp3)],
                   check=True)
    raw.unlink()
    return dur(mp3)


bad = [cid for cid, it in items.items()
       if not (6.2 <= len(it["text"]) / dur(OUT / f"{cid}.mp3") <= 7.0)]
print("조정 대상:", bad, flush=True)

for cid in bad:
    it = items[cid]
    speed, best, used = 110, None, None
    for attempt in range(1, 6):
        used = speed
        s = render_at(it, speed, OUT / f"{cid}.mp3")
        if s is None:
            break
        rate = len(it["text"]) / s
        print(f"{cid} speed={speed}: {s:.1f}초 {rate:.2f}자/초", flush=True)
        if best is None or abs(rate - TARGET) < abs(best[1] - TARGET):
            best = (speed, rate)
        if 6.2 <= rate <= 7.0:
            break
        speed = max(95, min(140, round(speed * rate / TARGET)))
    if best and used != best[0]:
        render_at(it, best[0], OUT / f"{cid}.mp3")
    print(f"{cid} 확정: speed={best[0]}, {best[1]:.2f}자/초", flush=True)

manifest, total = [], 0.0
for it in items.values():
    mp3 = OUT / f"{it['id']}.mp3"
    d = dur(mp3)
    manifest.append({"id": it["id"], "file": mp3.name, "seconds": round(d, 1)})
    total += d
(OUT / "manifest.json").write_text(
    json.dumps({"items": manifest}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료: 총 {total / 60:.1f}분 ({total:.0f}초)")
