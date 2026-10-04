#!/usr/bin/env python3
"""개편 후 변경된 클립만 재합성한다. 문구가 그대로인 클립은 기존 파일을 새 id로 재사용한다."""
import json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "audio18"
VOICE = "avocado_v2:qvd_04433"
new_items = json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))["items"]
old_items = json.loads((ROOT / "review" / "narration.prev.json").read_text(encoding="utf-8"))["items"]
old_by_text = {it["text"]: it["id"] for it in old_items}

# 1) 재사용: 기존 파일을 새 id 이름으로 복사 (합성이 덮어쓰기 전에 먼저)
for it in new_items:
    src_id = old_by_text.get(it["text"])
    if src_id and src_id != it["id"]:
        src, dst = OUT / f"{src_id}.mp3", OUT / f"{it['id']}.mp3"
        if src.exists():
            dst.write_bytes(src.read_bytes())
            print("REUSE", src_id, "->", it["id"], flush=True)

# 2) 변경분 합성 + 정규화
made, failed = [], []
for it in new_items:
    if it["text"] in old_by_text:
        continue
    mp3 = OUT / f"{it['id']}.mp3"
    raw = OUT / f"{it['id']}.raw.mp3"
    r = subprocess.run(["/opt/hatch/bin/tts", "speak", "--voice", VOICE,
                        "--language", "ko", "--speed", "90",
                        "--output", str(raw), "--text-stdin"],
                       input=it["text"], capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not raw.exists():
        failed.append(it["id"])
        print("FAIL", it["id"], (r.stdout + r.stderr)[-300:], flush=True)
        continue
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                    "-af", "loudnorm=I=-24.4:TP=-2.0:LRA=11",
                    "-codec:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(mp3)],
                   check=True)
    raw.unlink()
    made.append(it["id"])
    print("OK", it["id"], flush=True)

if failed:
    print("실패:", failed)
    sys.exit(1)

# 3) 새 항목에 없는 옛 파일 정리
keep = {f"{it['id']}.mp3" for it in new_items}
for f in OUT.glob("*.mp3"):
    if f.name not in keep:
        f.unlink()
        print("DELETE stale", f.name, flush=True)

# 4) manifest 재생성 (전 항목 실측)
manifest, total = [], 0.0
for it in new_items:
    mp3 = OUT / f"{it['id']}.mp3"
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                "format=duration", "-of", "csv=p=0", str(mp3)],
                               capture_output=True, text=True).stdout.strip())
    manifest.append({"id": it["id"], "file": mp3.name, "seconds": round(dur, 1)})
    total += dur
(OUT / "manifest.json").write_text(
    json.dumps({"items": manifest}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"완료: 신규 합성 {len(made)}개, 총 {total / 60:.1f}분 ({total:.0f}초)")
