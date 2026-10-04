#!/usr/bin/env python3
"""속도 이상 클립 3차 교정.

- 느린 클립: secant 보간으로 속도 탐색 (fix2의 방향 오류 정정). 실패 시 문장 분할 합성.
- 빠른/경계 클립: atempo로 자/초를 TARGET에 맞춤 (피치 유지).
- 정상 범위(6.2~7.0) 클립은 건드리지 않는다.
"""
import json, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "audio18"
VOICE = "avocado_v2:qvd_04433"
TARGET = 6.55
LO, HI = 6.2, 7.0
items = {it["id"]: it for it in json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))["items"]}


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                 "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout.strip())


def render_at(it, speed, mp3, text=None):
    raw = mp3.with_suffix(".raw.mp3") if mp3.suffix == ".mp3" else pathlib.Path(str(mp3) + ".raw.mp3")
    r = subprocess.run(["/opt/hatch/bin/tts", "speak", "--voice", VOICE,
                        "--language", "ko", "--speed", str(speed),
                        "--output", str(raw), "--text-stdin"],
                       input=text if text is not None else it["text"],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not raw.exists():
        print("FAIL", it["id"], (r.stdout + r.stderr)[-200:], flush=True)
        return None
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                    "-af", "loudnorm=I=-24.4:TP=-2.0:LRA=11",
                    "-codec:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(mp3)],
                   check=True)
    raw.unlink()
    return dur(mp3)


def rate_of(cid):
    return len(items[cid]["text"]) / dur(OUT / f"{cid}.mp3")


rates = {cid: rate_of(cid) for cid in items}
slow = [c for c, r in rates.items() if r < LO]
fast = [c for c, r in rates.items() if r > HI]
print("느린 클립:", [(c, round(rates[c], 2)) for c in slow], flush=True)
print("빠른 클립:", [(c, round(rates[c], 2)) for c in fast], flush=True)


def fix_slow(cid):
    it = items[cid]
    hist = []  # (speed, rate)
    speed = 110
    best = None
    for attempt in range(1, 5):
        s = render_at(it, speed, OUT / f"{cid}.mp3")
        if s is None:
            break
        rate = len(it["text"]) / s
        hist.append((speed, rate))
        print(f"{cid} speed={speed}: {s:.1f}초 {rate:.2f}자/초", flush=True)
        if best is None or abs(rate - TARGET) < abs(best[1] - TARGET):
            best = (speed, rate)
        if LO <= rate <= HI:
            print(f"{cid} 확정(속도 탐색): speed={speed}, {rate:.2f}자/초", flush=True)
            return
        # 다음 속도: 실측 2점으로 보간, 안 되면 +20
        nxt = None
        if len(hist) >= 2:
            (s1, r1), (s2, r2) = hist[-2], hist[-1]
            if s2 != s1 and (r2 - r1) / (s2 - s1) > 0.02:
                nxt = s2 + (TARGET - r2) / ((r2 - r1) / (s2 - s1))
        if nxt is None:
            nxt = speed + 20
        speed = max(90, min(170, round(nxt)))
    if best and best[0] != hist[-1][0]:
        render_at(it, best[0], OUT / f"{cid}.mp3")
    r = rate_of(cid)
    if LO <= r <= HI:
        print(f"{cid} 확정(best 채택): {r:.2f}자/초", flush=True)
        return
    print(f"{cid} 속도 탐색 실패({r:.2f}자/초) -> 문장 분할 합성", flush=True)
    fix_by_split(cid)


def fix_by_split(cid):
    it = items[cid]
    sents = [s.strip() for s in it["text"].split(". ") if s.strip()]
    sents = [s if s.endswith(".") else s + "." for s in sents]
    tmp = pathlib.Path(tempfile.mkdtemp(dir=ROOT))
    parts = []
    for i, sent in enumerate(sents):
        p = tmp / f"part{i:02d}.mp3"
        s = render_at(it, 90, p, text=sent)
        if s is None:
            print(f"{cid} 분할 합성 실패: 문장 {i}", flush=True)
            return
        parts.append(p)
        print(f"{cid} 문장 {i}: {s:.1f}초 {len(sent)/s:.2f}자/초", flush=True)
    # 무음 0.15초를 사이에 넣어 연결
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
    r = rate_of(cid)
    print(f"{cid} 확정(문장 분할): {r:.2f}자/초", flush=True)


for cid in slow:
    fix_slow(cid)

for cid in fast:
    mp3 = OUT / f"{cid}.mp3"
    r = rates[cid]
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
