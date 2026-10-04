#!/usr/bin/env python3
"""BotStory 스타일 검증기 — narration.json이 BotStory 규격에 맞는지 실측한다.

기준 (BotStory edu/why-ai-bots/narration.json 32클립 16,287자 실측):
- 해요체 종결 비율 99% 이상 (합니다체는 엔딩 감사 1문장만 허용)
- 아라비아 숫자 0개 (전부 한글 수사)
- 문장 평균 30~35자, 70자 초과 문장은 경고
- 의문문 비율 3% 이하 (클립당 1개 이하 목표)
사용법: python style_check.py <narration.json> [narration.json ...]
"""
import json, re, sys

HAEYO = re.compile(r"(요|죠)$")
HAPNIDA = re.compile(r"(입니다|됩니다|합니다|입니까|입니다|됩니다|니다|이다)$")

def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]

def check(path):
    d = json.load(open(path, encoding="utf-8-sig"))
    items = d["items"] if isinstance(d, dict) else d
    total_sent, haeyo, hapnida, other = 0, 0, 0, 0
    long_sents, digits, questions = [], [], 0
    lens = []
    for it in items:
        for s in split_sentences(it.get("text", "")):
            total_sent += 1
            lens.append(len(s))
            core = s.rstrip(".?!").strip()
            if re.search(r"[0-9]", s):
                digits.append(s[:40])
            if s.endswith("?"):
                questions += 1
            if len(s) > 70:
                long_sents.append((len(s), s[:40]))
            if HAEYO.search(core):
                haeyo += 1
            elif HAPNIDA.search(core):
                hapnida += 1
            else:
                other += 1
    avg = sum(lens) / len(lens) if lens else 0
    print(f"== {path}")
    print(f"문장 {total_sent}개 | 평균 {avg:.1f}자 | 의문문 {questions} ({questions/total_sent*100:.1f}%)")
    print(f"해요체 {haeyo} ({haeyo/total_sent*100:.1f}%) | 합니다체 {hapnida} | 기타 종결 {other}")
    print(f"아라비아 숫자 포함 문장 {len(digits)}개 | 70자 초과 {len(long_sents)}개")
    for n, s in long_sents[:5]:
        print(f"  [장문 {n}자] {s}…")
    for s in digits[:5]:
        print(f"  [숫자] {s}…")
    ok = haeyo / total_sent >= 0.99 and not digits
    print("판정:", "BotStory 규격 통과" if ok else "미달 — 해요체 비율 또는 숫자 표기 확인 필요")
    return ok

if __name__ == "__main__":
    results = [check(p) for p in sys.argv[1:]]
    sys.exit(0 if all(results) else 1)
