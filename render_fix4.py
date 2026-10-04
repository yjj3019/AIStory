#!/usr/bin/env python3
"""마무리 교정.

- 고속 파라미터로 맞춘 08·14·15장을 문장 분할 합성(속도 90)으로 교체한다.
- 12장은 atempo로 목표치에 미세 보정한다.
- manifest를 재생성한다.
"""
import json, pathlib, subprocess, tempfile

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "audio18"
VOICE = "avocado_v2:qvd_04433"
TARGET = 6.55
items = {it["id"]: it for it in json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))["items"]}


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                 "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout.strip())


def render_text(text, speed, mp3):
    raw = pathlib.Path(str(mp3) + ".raw.mp3")
    r = subprocess.run(["/opt/hatch/bin/tts", "speak", "--voice", VOICE,
                        "--language", "ko", "--speed", str(speed),
                        "--output", str(raw), "--text-stdin"],
                       input=text, capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not raw.exists():
        print("FAIL", (r.stdout + r.stderr)[-200:], flush=True)
        return None
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                    "-af", "loudnorm=I=-24.4:TP=-2.0:LRA=11",
                    "-codec:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(mp3)],
                   check=True)
    raw.unlink()
    return dur(mp3)


def rate_of(cid):
    return len(items[cid]["text"]) / dur(OUT / f"{cid}.mp3")


def fix_by_split(cid):
    it = items[cid]
    sents = [s.strip() for s in it["text"].split(". ") if s.strip()]
    sents = [s if s.endswith(".") else s + "." for s in sents]
    tmp = pathlib.Path(tempfile.mkdtemp(dir=ROOT))
    parts = []
    for i, sent in enumerate(sents):
        p = tmp / f"part{i:02d}.mp3"
        if render_text(sent, 90, p) is None:
            print(f"{cid} 분할 합성 실패: 문장 {i}", flush=True)
            return
        parts.append(p)
    sil = tmp / "sil.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.15",
                    "-codec:a", "libmp3lame", "-b:a", "128k", str(sil)], check=True)
    lst = tmp / "list.txt"
    lines = []
    for i, p in enumerate(parts):
        lines.append(f"file '{p}'")
        if i < len(parts) - 1:
            lines.append(f"file '{sil}'")
    lst.write_text("\n".join(lines), encoding="utf-8")
    joined = tmp / "joined.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-codec:a", "libmp3lame", "-b:a", "128k",
                    "-ar", "44100", str(joined)], check=True)
    mp3 = OUT / f"{cid}.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined),
                    "-af", "loudnorm=I=-24.4:TP=-2.0:LRA=11",
                    "-codec:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(mp3)],
                   check=True)
    print(f"{cid} 확정(문장 분할): {rate_of(cid):.2f}자/초", flush=True)


for cid in ("08-scene", "14-scene", "15-scene"):
    fix_by_split(cid)

cid = "12-scene"
mp3 = OUT / f"{cid}.mp3"
r = rate_of(cid)
factor = TARGET / r
tmp = mp3.with_suffix(".tmp.mp3")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
                "-af", f"atempo={factor:.3f},loudnorm=I=-24.4:TP=-2.0:LRA=11",
                "-codec:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(tmp)],
               check=True)
tmp.replace(mp3)
print(f"{cid} atempo {factor:.3f}: {r:.2f} -> {rate_of(cid):.2f}자/초", flush=True)

manifest, total = [], 0.0
for it in items.values():
    mp3 = OUT / f"{it['id']}.mp3"
    d = dur(mp3)
    manifest.append({"id": it["id"], "file": mp3.name, "seconds": round(d, 1)})
    total += d
(OUT / "manifest.json").write_text(
    json.dumps({"items": manifest}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료: 총 {total / 60:.1f}분 ({total:.0f}초)")
