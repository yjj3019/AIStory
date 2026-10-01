#!/usr/bin/env python
"""audio18/ 정합성 검증 (렌더 직후 실행).

  python .agent/sim_audio.py --root C:/AI-Codding/claude/AIStory

검사
 A. 파일 세트: 대본의 20개 id 마다 wav·mp3·sha1 존재, sha1 == 대본 문구 해시, manifest 의 id/문구 해시 일치
 B. 길이·속도: wav↔mp3↔manifest 길이 오차, 클립별 글자/초(cps) 이상치, 총 길이
 C. 음질 이상: 과도한 무음(중간 무음 >3초), 무음에 가까운 파일, 클리핑
 D. 자막 어긋남 추정: 글자 수 비율로 예측한 문장 경계 vs 실제 무음 구간 (추정치, 정확한 값 아님)
종료코드 0=정상, 1=문제 있음
"""
import argparse, hashlib, json, pathlib, re, statistics, subprocess, sys

sys.stdout.reconfigure(encoding="utf-8")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe_dur(p):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def silences(p, noise="-35dB", d=0.25):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-af", f"silencedetect=noise={noise}:d={d}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [(float(a), float(b)) for a, b in re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", r.stderr)]
    out = []
    for i, s in enumerate(starts):
        if i < len(ends):
            out.append((s, ends[i][0], ends[i][1]))
    return out


def volume(p):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    x = re.search(r"max_volume: (-?[\d.]+) dB", r.stderr)
    return (float(m.group(1)) if m else None, float(x.group(1)) if x else None)


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in parts if s]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--audio", default="audio18")
    ap.add_argument("--narration", default="narration.json")
    ap.add_argument("--report", default=None)
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    ad = root / a.audio
    nar = json.loads((root / a.narration).read_text(encoding="utf-8"))
    items = nar["items"]
    problems, notes = [], []
    rows = []

    man = None
    mp = ad / "manifest.json"
    if mp.exists():
        man = {x["id"]: x for x in json.loads(mp.read_text(encoding="utf-8"))["items"]}
    else:
        problems.append("manifest.json 없음")

    for it in items:
        i = it["id"]
        h = hashlib.sha1(it["text"].encode("utf-8")).hexdigest()
        wav, mp3, sha = ad / f"{i}.wav", ad / f"{i}.mp3", ad / f"{i}.sha1"
        for f in (wav, mp3, sha):
            if not f.exists():
                problems.append(f"{i}: {f.name} 없음")
        if sha.exists() and sha.read_text().strip() != h:
            problems.append(f"{i}: sha1 사이드카가 대본 문구와 다름(낡은 렌더)")
        if man is not None:
            m = man.get(i)
            if not m:
                problems.append(f"{i}: manifest 에 없음")
            elif m.get("text_sha1") != h:
                problems.append(f"{i}: manifest text_sha1 이 대본과 다름")
        dw = probe_dur(wav) if wav.exists() else None
        dm = probe_dur(mp3) if mp3.exists() else None
        ds = man[i]["seconds"] if man and i in man else None
        for name, v in (("wav", dw), ("mp3", dm), ("manifest", ds)):
            if v is None:
                problems.append(f"{i}: {name} 길이를 읽지 못함")
        if dw and dm and abs(dw - dm) > 0.35:
            problems.append(f"{i}: wav {dw:.2f}s ↔ mp3 {dm:.2f}s 길이 불일치")
        if dw and ds and abs(dw - ds) > 0.35:
            problems.append(f"{i}: wav {dw:.2f}s ↔ manifest {ds:.2f}s 불일치")
        rows.append({"id": i, "chars": len(it["text"]), "wav": dw, "mp3": dm, "man": ds, "it": it})

    # B. 속도 이상치
    cps = [(r["chars"] / r["wav"]) for r in rows if r["wav"]]
    med = statistics.median(cps) if cps else 0
    for r in rows:
        if r["wav"]:
            r["cps"] = r["chars"] / r["wav"]
            if med and (r["cps"] < med * 0.75 or r["cps"] > med * 1.25):
                problems.append(f"{r['id']}: 속도 이상치 {r['cps']:.2f}자/초 (중앙값 {med:.2f}) — 잘림/중복/느린 낭독 의심")
    total = sum(r["wav"] or 0 for r in rows)

    # C·D
    drift_rows = []
    for r in rows:
        w = ad / f"{r['id']}.wav"
        if not w.exists() or not r["wav"]:
            continue
        mean, mx = volume(w)
        r["mean"], r["max"] = mean, mx
        if mean is not None and mean < -38:
            problems.append(f"{r['id']}: 평균 음량 {mean} dB — 무음에 가까움")
        if mx is not None and mx >= -0.1:
            notes.append(f"{r['id']}: 최대 {mx} dB — 클리핑 가능")
        sil = silences(w)
        dur = r["wav"]
        mid = [s for s in sil if s[0] > 0.6 and s[1] < dur - 0.6]   # 앞뒤 무음 제외
        long_mid = [s for s in mid if s[2] > 3.0]
        if long_mid:
            problems.append(f"{r['id']}: 중간 무음 {max(x[2] for x in long_mid):.1f}초 — 낭독 끊김 의심")
        # 자막 어긋남 추정
        sents = split_sentences(r["it"]["text"])
        if len(sents) >= 3:
            tot = sum(len(s) for s in sents)
            acc, pred = 0, []
            for s in sents[:-1]:
                acc += len(s)
                pred.append(dur * acc / tot)
            top = sorted(sorted(mid, key=lambda s: -s[2])[: len(pred)], key=lambda s: s[0])
            if len(top) == len(pred):
                act = [(s[0] + s[1]) / 2 for s in top]
                d = [abs(p - q) for p, q in zip(pred, act)]
                drift_rows.append((r["id"], statistics.mean(d), max(d), len(sents)))
            else:
                notes.append(f"{r['id']}: 무음 {len(mid)}개 < 문장 경계 {len(pred)}개 — 어긋남 추정 생략")

    # 리포트
    L = []
    L.append(f"# audio18 시뮬레이션 리포트\n\n- 클립 {len(rows)}개, 총 {total/60:.1f}분, 중앙 속도 {med:.2f}자/초")
    L.append(f"- manifest: {'있음' if man else '없음'}\n")
    L.append("| id | 글자 | wav(s) | mp3(s) | manifest(s) | 자/초 | 평균dB |\n|---|---|---|---|---|---|---|")
    for r in rows:
        f = lambda v: f"{v:.1f}" if isinstance(v, (int, float)) else "-"
        L.append(f"| {r['id']} | {r['chars']} | {f(r['wav'])} | {f(r['mp3'])} | {f(r['man'])} | {f(r.get('cps'))} | {r.get('mean','-')} |")
    if drift_rows:
        L.append("\n## 자막 하이라이트 어긋남 추정 (글자 수 비율 vs 실제 무음, 초)\n\n| id | 문장 | 평균 | 최대 |\n|---|---|---|---|")
        for i, m, x, n in drift_rows:
            L.append(f"| {i} | {n} | {m:.1f} | {x:.1f} |")
        L.append(f"\n전체 평균 {statistics.mean(x[1] for x in drift_rows):.1f}초, 최악 {max(x[2] for x in drift_rows):.1f}초 (추정치)")
    L.append("\n## 문제\n" + ("\n".join(f"- {p}" for p in problems) if problems else "- 없음"))
    if notes:
        L.append("\n## 참고\n" + "\n".join(f"- {n}" for n in notes))
    text = "\n".join(L)
    print(text)
    if a.report:
        pathlib.Path(a.report).write_text(text, encoding="utf-8")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
