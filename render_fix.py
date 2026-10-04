#!/usr/bin/env python3
"""자/초가 비정상인 클립을 정상 범위(5.5~7.4)에 들 때까지 재합성한다 (최대 4회)."""
import json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "audio18"
VOICE = "avocado_v2:qvd_04433"
items = {it["id"]: it for it in json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))["items"]}


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                 "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout.strip())


def render(it, mp3):
    raw = mp3.with_suffix(".raw.mp3")
    r = subprocess.run(["/opt/hatch/bin/tts", "speak", "--voice", VOICE,
                        "--language", "ko", "--speed", "90",
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


bad = []
for cid, it in items.items():
    p = OUT / f"{cid}.mp3"
    if p.exists() and not (5.5 <= len(it["text"]) / dur(p) <= 7.4):
        bad.append(cid)
print("이상 클립:", bad, flush=True)

for cid in bad:
    it = items[cid]
    for attempt in range(1, 5):
        s = render(it, OUT / f"{cid}.mp3")
        if s is None:
            continue
        rate = len(it["text"]) / s
        print(f"{cid} 시도{attempt}: {s:.1f}초 {rate:.2f}자/초", flush=True)
        if 5.5 <= rate <= 7.4:
            break
    else:
        print("경고: 범위 밖 유지", cid, flush=True)

manifest, total = [], 0.0
for it in json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))["items"]:
    mp3 = OUT / f"{it['id']}.mp3"
    d = dur(mp3)
    manifest.append({"id": it["id"], "file": mp3.name, "seconds": round(d, 1)})
    total += d
(OUT / "manifest.json").write_text(
    json.dumps({"items": manifest}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료: 총 {total / 60:.1f}분 ({total:.0f}초)")
