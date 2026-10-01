#!/usr/bin/env python
"""STT(faster-whisper) 로 렌더된 낭독을 다시 받아써서 대본과 비교한다.

  stt-venv\\Scripts\\python.exe .agent/stt_check.py --root C:/AI-Codding/claude/AIStory [--only 11-scene,17-scene]

산출: .agent/stt_report.md (클립별 일치율·어긋난 구간), .agent/stt_raw/<id>.json (단어별 시각),
      .agent/sync.json (문장별 실측 시작/끝 시각 — 자막 싱크용)
※ 프롬프트(initial_prompt)를 주지 않는다. 대본 철자를 알려 주면 잘못 읽은 것도 맞게 받아써서 검증이 무의미해진다.
"""
import argparse, difflib, json, pathlib, re, statistics, subprocess, sys, time

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

# 영문·약어 → 한글 읽기 (STT 출력과 대본 양쪽에 같은 규칙을 적용해 표기 차이를 흡수한다)
GLOSSARY = [
    ("Attention Is All You Need", "어텐션이즈올유니드"), ("Thinking Machines Lab", "씽킹머신스랩"), ("Thinking Machines", "씽킹머신스"),
    ("Character.AI", "캐릭터에이아이"), ("Essential AI", "에센셜에이아이"), ("Adept AI", "어뎁트에이아이"), ("Discovery Loop", "디스커버리루프"),
    ("Eureka Labs", "유레카랩스"), ("AMI Labs", "에이엠아이랩스"), ("DNNresearch", "디엔엔리서치"), ("post-money", "포스트머니"),
    ("Series H", "시리즈에이치"), ("OpenAI", "오픈에이아이"), ("Anthropic", "앤트로픽"), ("ChatGPT", "챗지피티"), ("DeepSeek", "딥시크"),
    ("LawZero", "로제로"), ("Mistral", "미스트랄"), ("Cohere", "코히어"), ("GPT-3", "지피티삼"), ("GPT-2", "지피티이"), ("GPT-1", "지피티일"),
    ("GPT", "지피티"), ("xAI", "엑스에이아이"), ("XAI", "엑스에이아이"), ("SSI", "에스에스아이"), ("CEO", "씨이오"), ("CTO", "씨티오"),
    ("GPU", "지피유"), ("CPU", "씨피유"), ("TPU", "티피유"), ("AGI", "에이지아이"), ("CUDA", "쿠다"), ("CVPR", "씨브이피알"), ("LISP", "리스프"),
    ("MIT", "엠아이티"), ("XOR", "엑스오알"), ("FAIR", "페어"), ("Azure", "애저"), ("AI", "에이아이"), ("X", "엑스"),
    ("AMI", "에이엠아이"), ("DNN", "디엔엔"), ("ceo", "씨이오"),
]
# STT 가 자주 내는 대안 표기(같은 발음). 비교 전에 표준형으로 바꾼다.
ALIASES = [("오픈 AI", "오픈에이아이"), ("오픈에이아이", "오픈에이아이"), ("싱킹머신스", "씽킹머신스"), ("싱킹머신즈", "씽킹머신스"), ("씽킹머신즈", "씽킹머신스"),
           ("앤스로픽", "앤트로픽"), ("앤트로피", "앤트로픽"), ("로우제로", "로제로"), ("로 제로", "로제로"), ("딥씨크", "딥시크"), ("코히어", "코히어"), ("코헤어", "코히어")]

D = "영일이삼사오육칠팔구"


def sino(n):
    if n == 0:
        return "영"
    out = ""
    units = [(10 ** 12, "조"), (10 ** 8, "억"), (10 ** 4, "만")]
    for u, name in units:
        if n >= u:
            q, n = divmod(n, u)
            out += sino(q) + name
    for u, name in ((1000, "천"), (100, "백"), (10, "십")):
        if n >= u:
            q, n = divmod(n, u)
            out += ("" if q == 1 else D[q]) + name
    if n:
        out += D[n]
    return out


def read_number(tok):
    tok = tok.replace(",", "")
    if "." in tok:
        a, b = tok.split(".", 1)
        return sino(int(a)) + "점" + "".join(D[int(c)] for c in b if c.isdigit())
    return sino(int(tok))


def to_reading(text):
    """대본/STT 문자열 → 한글 음절만 남긴 비교용 문자열 + 토큰별 원문 추적"""
    s = text
    for k, v in ALIASES:
        s = s.replace(k, v)
    for k, v in GLOSSARY:
        s = re.sub(re.escape(k), v, s, flags=re.I if k.isupper() or k[0].isupper() else 0)
    s = re.sub(r"(\d)\s*월", lambda m: {"6": "유", "10": "시"}.get(m.group(1), read_number(m.group(1))) + "월", s)
    s = re.sub(r"\d[\d,]*(?:\.\d+)?", lambda m: read_number(m.group(0)), s)
    return "".join(ch for ch in s if "가" <= ch <= "힣")


MULTI = [k for k, _ in GLOSSARY if " " in k]


def tokens_with_offsets(text):
    """공백 단위 토큰과 그 읽기의 (시작,끝) 오프셋 — 어긋난 구간을 원문 단어로 되짚기 위해.
    여러 단어로 된 용어(Adept AI 등)는 한 토큰으로 묶어서 읽기 변환이 깨지지 않게 한다."""
    t = text
    for k in MULTI:
        t = re.sub(re.escape(k), k.replace(" ", "_"), t, flags=re.I)
    toks, pos, acc = [], 0, ""
    for tk in t.split():
        tk = tk.replace("_", " ")
        r = to_reading(tk)
        toks.append((tk, len(acc), len(acc) + len(r)))
        acc += r
    return toks, acc


def split_sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def fmt(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--audio", default="audio18")
    ap.add_argument("--narration", default="narration.json")
    ap.add_argument("--model", default=str(pathlib.Path.home() / "whisper-models" / "large-v3"))
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=None)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--ext", default="wav")
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    here = pathlib.Path(__file__).resolve().parent
    out = pathlib.Path(a.out) if a.out else here
    raw = out / "stt_raw"
    raw.mkdir(parents=True, exist_ok=True)
    nar = json.loads((root / a.narration).read_text(encoding="utf-8"))["items"]
    only = {x for x in a.only.split(",") if x}
    from faster_whisper import WhisperModel
    t0 = time.time()
    model = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=a.threads)
    print(f"모델 로딩 {time.time() - t0:.0f}s", flush=True)

    rep, sync, summary, listen, anchors = [], {}, [], [], {}
    for it in nar:
        cid = it["id"]
        if only and cid not in only:
            continue
        f = root / a.audio / f"{cid}.{a.ext}"
        if not f.exists():
            print("없음", f); continue
        rj = raw / f"{cid}.json"
        if rj.exists():
            words = json.loads(rj.read_text(encoding="utf-8"))["words"]
        else:
            t1 = time.time()
            pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                                 capture_output=True, check=True).stdout
            arr = np.frombuffer(pcm, dtype=np.float32)
            segs, info = model.transcribe(arr, language="ko", beam_size=5, condition_on_previous_text=False,
                                          word_timestamps=True, vad_filter=False, temperature=0.0)
            words = []
            for sg in segs:
                for w in sg.words or []:
                    words.append({"w": w.word, "s": round(w.start, 2), "e": round(w.end, 2)})
            rj.write_text(json.dumps({"id": cid, "dur": round(info.duration, 2), "words": words}, ensure_ascii=False), encoding="utf-8")
            print(f"{cid} STT {time.time() - t1:.0f}s (오디오 {info.duration:.0f}s)", flush=True)
        # Whisper 는 오디오 끝의 무음/여운에 "감사합니다" 같은 문구를 환각하는 경우가 많다.
        # 대본이 그 말로 끝나지 않고, 그 단어가 비정상적으로 짧게(<0.4초/음절 수 대비) 찍혔으면 버린다.
        while words and (words[-1]["e"] - words[-1]["s"]) < 0.06:     # 길이 0 에 가까운 끝부분 단어 = 환각(실제 낭독 단어는 0.1초 이상)
            words = words[:-1]
        HALL = re.compile(r"감사합니다|자막|시청|구독|좋아요|번역|제공|MBC|SBS|KBS")
        while words:
            last = to_reading(words[-1]["w"])
            tail = "".join(to_reading(w["w"]) for w in words[-6:])
            if not last:                      # 마침표·공백뿐인 꼬리 단어가 뒤에 있으면 환각 판정이 막히므로 먼저 걷어낸다
                words = words[:-1]
                continue
            if (HALL.search(last) or (HALL.search(tail) and len(last) >= 2)) and words[-1]["s"] >= max(w["e"] for w in words) - 4.0 \
               and not to_reading(it["text"]).endswith(last):
                words = words[:-1]
            else:
                break
        heard_txt = "".join(w["w"] for w in words)
        # 단어 → 읽기 오프셋 (시각 매핑용)
        hr, hmap = "", []
        for w in words:
            r = to_reading(w["w"])
            for _ in r:
                hmap.append(w)
            hr += r
        toks, er = tokens_with_offsets(it["text"])
        sm = difflib.SequenceMatcher(None, er, hr, autojunk=False)
        ratio = sm.ratio()
        ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
        bad = []
        for tag, i1, i2, j1, j2 in ops:
            if max(i2 - i1, j2 - j1) < 2:
                continue
            ex_tokens = [t for t, a0, b0 in toks if b0 > i1 and a0 < max(i2, i1 + 1)]
            tt = hmap[j1]["s"] if j1 < len(hmap) else (hmap[-1]["e"] if hmap else 0)
            bad.append((tag, "".join(er[i1:i2]), "".join(hr[j1:j2]), " ".join(ex_tokens[:6]), i1, tt))
            listen.append((cid, tt, " ".join(ex_tokens[:3]), "".join(er[i1:i2]), "".join(hr[j1:j2])))
        # 실측 문장 경계
        exp2heard = {}
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    exp2heard[i1 + k] = j1 + k
        sents = split_sentences(it["text"])
        cum, spans = 0, []
        for s in sents:
            n = len(to_reading(s))
            spans.append((cum, cum + n))
            cum += n
        dur = max((w["e"] for w in words), default=0)
        srow = []
        for (a0, b0), s in zip(spans, sents):
            def tm(idx, end):
                rng = range(idx, b0) if not end else range(idx - 1, a0 - 1, -1)
                for k in rng:
                    if k in exp2heard and exp2heard[k] < len(hmap):
                        return hmap[exp2heard[k]]["e" if end else "s"]
                return None
            srow.append({"text": s, "start": tm(a0, False), "end": tm(b0, True)})
        sync[cid] = srow
        # 자막 보정용 앵커: [글자 비율, 실제 시각]. 문장 시작·끝을 모두 넣어 문장 사이 쉼도 반영한다.
        # 좌표 = 공백을 뺀 글자 수 누적 비율. 원본형(문단)·슬라이드(문장) 두 페이지가 같은 방식으로 경계를 계산한다.
        nws = lambda s: len(re.sub(r"\s", "", s))
        # 낭독용 표기 치환이 있으면 화면 문구(display_text)의 문장 길이를 좌표로 쓴다 — 페이지는 화면 문구로 경계를 계산한다.
        dsents = split_sentences(it.get("display_text", it["text"]))
        lens = [nws(x) for x in dsents] if len(dsents) == len(srow) else [nws(s["text"]) for s in srow]
        tot_c = sum(lens) or 1
        cum, anc = 0, [[0.0, 0.0]]
        for s, ln in zip(srow, lens):
            f0 = cum / tot_c
            cum += ln
            f1 = cum / tot_c
            for f, tv in ((f0, s["start"]), (f1, s["end"])):
                if tv is not None and f >= anc[-1][0] and tv >= anc[-1][1]:
                    anc.append([round(f, 4), round(tv, 2)])
        if anc[-1][0] < 1.0:
            anc.append([1.0, round(max(dur, anc[-1][1]), 2)])
        anchors[cid] = anc
        tot = sum(b - a0 for a0, b in spans) or 1
        drifts = []
        acc = 0
        for (a0, b0), r in zip(spans, srow):
            acc += b0 - a0
            if r["end"] is not None:
                drifts.append(abs(dur * acc / tot - r["end"]))
        summary.append((cid, ratio, len(bad), statistics.mean(drifts) if drifts else None, max(drifts) if drifts else None))
        rep.append(f"\n### {cid}  일치율 {ratio*100:.1f}%  (어긋난 구간 {len(bad)}개)")
        for tag, e, h, tk, pos, tt in sorted(bad, key=lambda x: -max(len(x[1]), len(x[2])))[:12]:
            rep.append(f"- [{tag}] {fmt(tt)}  대본 「{e}」 ↔ 들린 것 「{h}」  ← 원문 토큰: {tk}")

    L = ["# STT 검증 리포트 (faster-whisper large-v3, int8, 프롬프트 없음)\n",
         "일치율은 숫자·영문을 한글 읽기로 바꾼 음절열 기준. 표기 차이(예: 어절 나눔)는 이미 흡수했으나 완전하지 않으므로 어긋난 구간은 사람이 판정한다.\n",
         "| id | 일치율 | 어긋난 구간 | 자막 어긋남 평균(초) | 최대(초) |", "|---|---|---|---|---|"]
    for cid, r, n, m, x in summary:
        L.append(f"| {cid} | {r*100:.1f}% | {n} | {'-' if m is None else f'{m:.1f}'} | {'-' if x is None else f'{x:.1f}'} |")
    ms = [m for _, _, _, m, _ in summary if m is not None]
    if ms:
        L.append(f"\n자막 어긋남(글자 수 비율 예측 vs STT 실측 문장 끝): 평균 {statistics.mean(ms):.1f}초, 최악 {max(x for *_, x in summary if x is not None):.1f}초")
    L += rep
    (out / "stt_report.md").write_text("\n".join(L), encoding="utf-8")
    (out / "sync.json").write_text(json.dumps(sync, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "audio_sync.json").write_text(json.dumps(anchors, separators=(",", ":")), encoding="utf-8")
    (out / "listen.md").write_text("# 청취 확인 목록 (STT 불일치 구간 — 시각은 해당 클립 안의 위치)\n\n| 클립 | 시각 | 원문 토큰 | 대본 읽기 | 들린 것 |\n|---|---|---|---|---|\n" +
                                   "\n".join(f"| {c} | {fmt(t)} | {tk} | {e} | {h} |" for c, t, tk, e, h in listen), encoding="utf-8")
    print("\n".join(L[:40]))


if __name__ == "__main__":
    main()
