#!/usr/bin/env python3
"""
AIStory.html 안의 SCENES 배열에서 내레이션 문장을 뽑아 narration.json 으로 저장한다.

HTML 을 유일한 원본으로 두기 위한 스크립트다.
문구를 고칠 때는 HTML 만 고치고 이 스크립트를 다시 돌리면 음성까지 동기화된다.

사용법:
    python extract_narration.py ../AIStory.html -o narration.json
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

# 오프닝/엔딩은 HTML 의 SCENES 배열 밖에 있으므로 여기서 관리한다.
OPENING = {
    "id": "00-opening",
    "label": "오프닝",
    "lines": [
        "지금부터 인공지능을 만든 사람들의 이야기를 전해드립니다.",
        "1956년 다트머스에서 시작해 지금까지 이어진, 70년에 걸친 하나의 계보입니다.",
    ],
}
ENDING = {
    "id": "16-ending",
    "label": "엔딩",
    "lines": [
        "경쟁처럼 보이는 이 지형은, 실은 몇 사람에게서 갈라져 나온 하나의 계보였다.",
    ],
}

TAG = re.compile(r"<[^>]+>")


def strip_tags(s: str) -> str:
    """<span class="hi"> 같은 강조 태그를 제거한다."""
    return TAG.sub("", s).strip()


def parse_scenes(html: str) -> list[dict]:
    try:
        body = html.split("const SCENES = [", 1)[1].split("\n];", 1)[0]
    except IndexError:
        sys.exit("SCENES 배열을 찾지 못했습니다. HTML 경로를 확인하세요.")

    years = re.findall(r"year:'([^']*)'", body)
    # lines:[ ... ] 블록을 장면 순서대로 수집
    line_blocks = re.findall(r"lines:\[(.*?)\n  \]", body, flags=re.S)

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
                "label": f"{i}장 · {year}",
                "lines": lines,
            }
        )
    return scenes


def main() -> None:
    ap = argparse.ArgumentParser(description="HTML에서 내레이션 텍스트 추출")
    ap.add_argument("html", help="AIStory.html 경로")
    ap.add_argument("-o", "--output", default="narration.json")
    args = ap.parse_args()

    html = pathlib.Path(args.html).read_text(encoding="utf-8")
    items = [OPENING] + parse_scenes(html) + [ENDING]

    for it in items:
        # OmniVoice 에 한 번에 넘길 문장. 줄 사이는 마침표 간격으로 자연스럽게 이어진다.
        it["text"] = " ".join(it["lines"])
        it["chars"] = len(it["text"])

    out = {
        "language": "ko",
        "title": "빛이 된 아이 — 인공지능 70년 이야기",
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
