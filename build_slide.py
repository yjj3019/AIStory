#!/usr/bin/env python3
"""AIStory.html 의 P / RIVALS / SCENES 데이터 블록을 slide.template.html 에 주입해
슬라이드형 페이지(AIStory-slide.html)를 생성한다.

문구의 유일한 원본은 AIStory.html 이다. 대사를 고쳤다면 AIStory.html 을 고친 뒤 이 스크립트를 다시 실행한다.

    python build_slide.py                       # AIStory.html -> AIStory-slide.html
    python build_slide.py --src X.html -o Y.html
"""
import argparse
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

# (상수명, 여는 정규식, 닫는 마커) — 닫는 마커는 줄 첫머리의 `};` / `];`
BLOCKS = [("P", "{", "\n};"), ("RIVALS", "{", "\n};"), ("SCENES", "[", "\n];")]


def extract(html: str, name: str, opener: str, closer: str) -> str:
    m = re.search("^const " + re.escape(name) + " = " + re.escape(opener), html, re.M)
    if not m:
        raise SystemExit(f"[오류] AIStory.html 에서 `const {name} = {opener}` 를 찾지 못했다 — 구조가 바뀌었는가?")
    end = html.find(closer, m.end())
    if end < 0:
        raise SystemExit(f"[오류] `{name}` 블록의 끝({closer.strip()})을 찾지 못했다.")
    return html[m.start(): end + len(closer)] + ";"


def main() -> None:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(here / "AIStory.html"))
    ap.add_argument("--template", default=str(here / "slide.template.html"))
    ap.add_argument("-o", "--out", default=str(here / "AIStory-slide.html"))
    a = ap.parse_args()

    src = Path(a.src).read_text(encoding="utf-8")
    tpl = Path(a.template).read_text(encoding="utf-8")
    if "/*DATA*/" not in tpl:
        raise SystemExit("[오류] 템플릿에 /*DATA*/ 마커가 없다.")

    data = "\n\n".join(extract(src, *b) for b in BLOCKS)
    Path(a.out).write_text(tpl.replace("/*DATA*/", data), encoding="utf-8", newline="\n")
    print(f"생성: {a.out}  (SCENES 원본 {a.src})")


if __name__ == "__main__":
    main()
