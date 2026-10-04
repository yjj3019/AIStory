#!/usr/bin/env python3
"""AIStory narration.json -> cloud TTS clips (voice B) + manifest.json."""
import json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "audio18"
OUT.mkdir(exist_ok=True)
VOICE = "avocado_v2:qvd_04433"
items = json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))["items"]

made, skipped, failed = [], [], []
for it in items:
    mp3 = OUT / f"{it['id']}.mp3"
    if mp3.exists() and mp3.stat().st_size > 10000:
        skipped.append(it["id"]); continue
    r = subprocess.run(["/opt/hatch/bin/tts", "speak", "--voice", VOICE,
                        "--language", "ko", "--speed", "90",
                        "--output", str(mp3), "--text-stdin"],
                       input=it["text"], capture_output=True, text=True, timeout=600)
    if r.returncode == 0 and mp3.exists():
        made.append(it["id"]); print("OK", it["id"], flush=True)
    else:
        failed.append(it["id"])
        print("FAIL", it["id"], (r.stdout + r.stderr)[-300:], flush=True)

# 후처리: -24.4 LUFS 정규화 + 실측 manifest (BotStory 완성 규격)
import wave
manifest = []
total = 0.0
for it in items:
    mp3 = OUT / f"{it['id']}.mp3"
    if not mp3.exists():
        continue
    tmp = OUT / f"{it['id']}.norm.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
                    "-af", "loudnorm=I=-24.4:TP=-2.0:LRA=11",
                    "-codec:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(tmp)],
                   check=True)
    tmp.replace(mp3)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                "format=duration", "-of", "csv=p=0", str(mp3)],
                               capture_output=True, text=True).stdout.strip())
    manifest.append({"id": it["id"], "file": mp3.name, "seconds": round(dur, 1)})
    total += dur
    print(f"{it['id']}: {dur:.1f}s", flush=True)

(OUT / "manifest.json").write_text(
    json.dumps({"items": manifest}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료: 생성 {len(made)}, 건너뜀 {len(skipped)}, 실패 {len(failed)}, 총 {total/60:.1f}분")
if failed:
    sys.exit(1)
