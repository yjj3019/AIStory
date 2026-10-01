#!/usr/bin/env python
"""listen/ 구간 파일을 서로 다른 Whisper 모델·조건으로 받아써 교차 확인한다.

  stt-venv\\Scripts\\python.exe .agent/cross_stt.py --listen C:/AI-Codding/claude/AIStory/listen

각 구간을 (모델 2종) x (프롬프트 없음 / 정답 철자 힌트) 로 돌려 "대본에 쓴 말"이 들리는지 본다.
 - 힌트를 줘도 정답이 안 나오면: 소리 자체가 어색하다는 강한 증거.
 - 힌트를 줘야만 나오면: 약한 증거(힌트가 결과를 끌어당길 수 있다).
 - 힌트 없이 나오면: 소리는 충분히 또렷하다.
"""
import argparse, json, pathlib, re, subprocess, sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

HINT = "일리야 수츠케버, 에이엠아이 랩스, 디엔엔 리서치, 씽킹 머신스 랩, 로 제로, 애저."
# 구간별로 "들려야 하는 말" (원문 표기 기준, 공백 제거 비교)
WANT = {"츠케": ["수츠케버", "수츠케", "서츠케버", "수츠께버"], "디엔엔": ["디엔엔"], "에이엠아이": ["에이엠아이", "AMI"]}


def load(p):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(pcm, dtype=np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="listen")
    ap.add_argument("--models", default="large-v3={0},turbo={1}".format(pathlib.Path.home() / "whisper-models" / "large-v3", pathlib.Path.home() / "whisper-models" / "large-v3-turbo"))
    ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args()
    ld = pathlib.Path(a.listen)
    rows = []
    for l in (ld / "INDEX.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\| (\d\d_\S+\.mp3) \| (\S+) \| (\S+) \| (.*?) \| (.*?) \| (.*?) \|", l)
        if m:
            rows.append(dict(file=m.group(1), clip=m.group(2), t=m.group(3), token=m.group(4), want=m.group(5), heard_full=m.group(6)))
    from faster_whisper import WhisperModel
    models = {}
    for spec in a.models.split(","):
        name, path = spec.split("=", 1)
        if not (pathlib.Path(path) / "model.bin").exists():
            print("모델 없음, 건너뜀:", name, path); continue
        models[name] = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=a.threads)
    res = {}
    for r in rows:
        audio = load(ld / r["file"])
        out = {}
        for mname, model in models.items():
            for cond, prompt in (("무힌트", None), ("힌트", HINT)):
                segs, _ = model.transcribe(audio, language="ko", beam_size=5, condition_on_previous_text=False,
                                           word_timestamps=True, temperature=0.0, initial_prompt=prompt)
                words = [w for s in segs for w in (s.words or [])]
                txt = "".join(w.word for w in words).strip()
                # 환각성 꼬리 제거(길이 0 단어)
                words = [w for w in words if (w.end - w.start) >= 0.06]
                txt = "".join(w.word for w in words).strip()
                out[f"{mname}/{cond}"] = (txt, [(w.word.strip(), round(w.probability, 2)) for w in words])
        res[r["file"]] = (r, out)
    # 보고
    L = ["# 교차 STT 결과 (구간 6.5초, 모델 x 힌트)\n", "※ '힌트'는 정답 철자를 initial_prompt 로 준 경우. 힌트로도 정답이 안 나오면 소리 자체가 어색하다는 강한 증거.\n"]
    verdict = []
    for f, (r, out) in res.items():
        L.append(f"## {f}  ({r['clip']} {r['t']})  원문 단어: {r['token']}  / 확인할 말: {r['want']}")
        key = next((k for k in WANT if k in r["want"] or k in r["token"]), None)
        ok = {}
        for cond, (txt, ws) in out.items():
            hit = key is not None and any(w in txt.replace(" ", "") for w in WANT[key])
            ok[cond] = hit
            L.append(f"- {cond}: {'O' if hit else 'X'}  「{txt}」")
        L.append("")
        nohint = [v for k, v in ok.items() if k.endswith("무힌트")]
        hint = [v for k, v in ok.items() if k.endswith("/힌트")]
        verdict.append((f, r["token"], sum(nohint), len(nohint), sum(hint), len(hint)))
    L.append("## 요약 (O 개수 / 모델 수)\n\n| 파일 | 원문 | 힌트 없이 | 힌트 있어도 |\n|---|---|---|---|")
    for f, tok, n1, d1, n2, d2 in verdict:
        L.append(f"| {f} | {tok} | {n1}/{d1} | {n2}/{d2} |")
    (ld / "CROSS.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[-(len(verdict) + 4):]))
    print("\n저장:", ld / "CROSS.md")


if __name__ == "__main__":
    main()
