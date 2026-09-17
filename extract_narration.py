#!/usr/bin/env python3
"""
교육/서사 HTML 안의 SCENES 배열에서 내레이션 문장을 뽑아 narration.json 으로 저장한다.

HTML 을 유일한 원본으로 두기 위한 스크립트다.
문구를 고칠 때는 HTML 만 고치고 이 스크립트를 다시 돌리면 음성까지 동기화된다.

클립 id 규칙 (장면 수 N에 동적):
    00-opening, 01-scene … NN-scene, (N+1)-ending
예: 교육 트랙 20장 → 00-opening + 01..20-scene + 21-ending = 22클립

사용법:
    python extract_narration.py education/why-ai-bots.html -o samples/narration.education-22.json
    python extract_narration.py AIStory.html -o narration.json
"""

import argparse
import json
import pathlib
import re
import sys

# Windows 콘솔 기본 코드페이지(cp949)는 en-dash(–) 등 일부 유니코드 문자를
# 인코딩하지 못해 UnicodeEncodeError로 즉시 죽는다. UTF-8로 강제 재설정한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

# 오프닝/엔딩 기본값 (교육 트랙). HTML에 OPENING_TEXT / ENDING_TEXT 가 있으면 그걸 우선한다.
# id 의 숫자 부분은 장면 수에 따라 main() 에서 다시 붙인다.
OPENING = {
    "id": "00-opening",
    "label": "오프닝",
    "lines": [
        "안녕하세요. 오늘은 제품 카탈로그를 읽지 않습니다. 사람들이 왜 AI 봇에 열광하는가만 따라가겠습니다. 시작점은 답만 남기고 일이 끝나지 않던 한계이고, 오픈소스와 에이전트 소셜을 거쳐 Grok Bot과 Meta Muse까지 온 길을 증거로 보겠습니다. 설명만 삼십 분이고, 질의 시간은 없습니다.",
    ],
}
ENDING = {
    "id": "21-ending",  # 기본값(20장 기준). 실제 id는 장면 수+1 로 덮어쓴다.
    "label": "엔딩",
    "lines": [
        "오늘은 왜 열광하는가만 따라갔습니다. 제품 이름은 바뀌어도, 실행 환경과 승인 경계를 먼저 적는 습관이 남으면 됩니다. 설명은 여기까지입니다. 들어 주셔서 감사합니다.",
    ],
}

DEFAULT_TITLE = "AI Bot 시대, 사람들은 왜 열광하는가"

TAG = re.compile(r"<[^>]+>")
OPENING_TEXT_RE = re.compile(
    r"const\s+OPENING_TEXT\s*=\s*('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")\s*;",
    re.S,
)
ENDING_TEXT_RE = re.compile(
    r"const\s+ENDING_TEXT\s*=\s*('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")\s*;",
    re.S,
)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def strip_tags(s: str) -> str:
    """<span class="hi"> 같은 강조 태그를 제거한다."""
    return TAG.sub("", s).strip()


def _unquote_js_string(literal: str) -> str:
    """JS 단일/이중 인용 문자열 리터럴을 파이썬 문자열로 푼다."""
    quote = literal[0]
    body = literal[1:-1]
    if quote == "'":
        return body.replace("\\'", "'").replace("\\\\", "\\")
    return body.replace('\\"', '"').replace("\\\\", "\\")


def parse_bookend_text(html: str, pattern: re.Pattern, fallback_lines: list[str]) -> list[str]:
    m = pattern.search(html)
    if not m:
        return list(fallback_lines)
    text = strip_tags(_unquote_js_string(m.group(1))).strip()
    return [text] if text else list(fallback_lines)


def parse_title(html: str) -> str:
    m = TITLE_RE.search(html)
    if not m:
        return DEFAULT_TITLE
    raw = strip_tags(m.group(1))
    # "AIStory · …" 형태면 뒤쪽만
    if "·" in raw:
        raw = raw.split("·", 1)[1].strip()
    return raw or DEFAULT_TITLE


def scene_label(index: int, year: str) -> str:
    """year 가 이미 'N장 · …' 이면 그대로, 아니면 'N장 · year'."""
    year = year.strip()
    if re.match(r"^\d+장\b", year):
        return year
    return f"{index}장 · {year}"


def parse_scenes(html: str) -> list[dict]:
    try:
        body = html.split("const SCENES = [", 1)[1].split("\n];", 1)[0]
    except IndexError:
        sys.exit("SCENES 배열을 찾지 못했습니다. HTML 경로를 확인하세요.")

    years = re.findall(r"year:\s*'([^']*)'", body)
    # lines:[ ... ] 블록을 장면 순서대로 수집 (들여쓰기 2칸 기준 + 느슨한 변형)
    line_blocks = re.findall(r"lines:\s*\[(.*?)\n\s*\]", body, flags=re.S)

    if len(years) != len(line_blocks):
        sys.exit(
            f"장면 수가 맞지 않습니다. year={len(years)}, lines={len(line_blocks)}"
        )

    scenes = []
    for i, (year, block) in enumerate(zip(years, line_blocks), start=1):
        raw = re.findall(r"'((?:[^'\\]|\\.)*)'", block)
        lines = [strip_tags(x.replace("\\'", "'")) for x in raw]
        lines = [x for x in lines if x]
        scenes.append(
            {
                "id": f"{i:02d}-scene",
                "label": scene_label(i, year),
                "lines": lines,
            }
        )
    return scenes


def ending_id(scene_count: int) -> str:
    return f"{scene_count + 1:02d}-ending"


def build_items(html: str) -> tuple[list[dict], str]:
    scenes = parse_scenes(html)
    n = len(scenes)
    opening_lines = parse_bookend_text(html, OPENING_TEXT_RE, OPENING["lines"])
    ending_lines = parse_bookend_text(html, ENDING_TEXT_RE, ENDING["lines"])
    opening = {
        "id": "00-opening",
        "label": OPENING["label"],
        "lines": opening_lines,
    }
    ending = {
        "id": ending_id(n),
        "label": ENDING["label"],
        "lines": ending_lines,
    }
    return [opening] + scenes + [ending], parse_title(html)


def main() -> None:
    ap = argparse.ArgumentParser(description="HTML에서 내레이션 텍스트 추출")
    ap.add_argument("html", help="교육/서사 HTML 경로 (SCENES + OPENING_TEXT/ENDING_TEXT)")
    ap.add_argument("-o", "--output", default="narration.json")
    args = ap.parse_args()

    html = pathlib.Path(args.html).read_text(encoding="utf-8")
    items, title = build_items(html)

    for it in items:
        # OmniVoice 에 한 번에 넘길 문장. 줄 사이는 마침표 간격으로 자연스럽게 이어진다.
        it["text"] = " ".join(it["lines"])
        it["chars"] = len(it["text"])

    out = {
        "language": "ko",
        "title": title,
        "items": items,
    }
    pathlib.Path(args.output).write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = sum(i["chars"] for i in items)
    print(f"{len(items)}개 항목, 총 {total}자 → {args.output}")
    print(f"예상 낭독 시간 약 {total / 320:.1f}분 (분당 320자 기준)")
    for i in items:
        print(f"  {i['id']:<12} {i['chars']:>4}자  {i['label']}")


if __name__ == "__main__":
    main()
