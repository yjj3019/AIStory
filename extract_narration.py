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
        "안녕하세요. 오늘은 인공지능의 발명품 이름을 늘어놓지 않으려고 해요. 지금 우리가 매일 쓰는 에이아이가 어떤 사람들 덕분에 여기까지 왔는지, 그 질문 하나만 따라가 볼게요.",
        "계보라는 말은 이 이야기에서 쓰는 비유예요. 사람들이 만나고 갈라지며 이어진 길이라는 뜻이에요. 출발점은 천구백오십년, 기계가 생각할 수 있느냐는 질문이에요.",
        "이야기는 두 부분으로 나뉘어요. 앞부분은 기술을 만든 사람들, 뒷부분은 회사를 세우고 갈라진 사람들의 이야기예요. 날짜와 숫자는 확인된 범위에서만 말씀드려요. 사람 이름을 외우기보다, 그 사람이 무엇을 배울 수 있게 만들었는지를 봐 주세요.",
    ],
}
# 부 구분 화면의 낭독 문구 — build_aistory.py 의 PART_TEXT 와 같은 문장을 유지한다.
PART_TEXT = {
    1: "기술의 계보, 첫 번째 부분이에요. 질문이 태어나고 겨울을 지나, 배우는 기계가 돌아오기까지의 이야기예요.",
    2: "회사와 사람의 시대, 두 번째 부분이에요. 기술을 나누겠다는 약속이 규모와 부딪히고, 사람들이 갈라져 나가는 이야기예요.",
}
PART_NAME = {1: "기술의 계보", 2: "회사와 사람의 시대"}
ENDING = {
    "id": "ending",   # main() 이 장 수를 세어 NN-ending 으로 확정한다
    "label": "엔딩",
    "lines": [
        "경쟁처럼 보이는 이 지형의 중심에는, 몇 사람에게서 갈라져 나온 하나의 계보가 있었다.",
    ],
}

TAG = re.compile(r"<[^>]+>")

# 낭독용 표기 치환 — TTS 에 넘기는 문구(narration.json)에만 적용하고 화면 문구(HTML)는 그대로 둔다.
# STT(Whisper) 받아쓰기로 실제 오독이 확인된 것만 넣는다(2026-10-01 시험 합성 17건으로 검증).
#   수츠케버 → "수츠케버"가 "수축해버"로 읽힘 / Thinking Machines Lab → "틴킹 메신 슬랩" / AMI Labs → "에이마이 랩스" /
#   LawZero → "러지로" / Azure → "에지어". DNNresearch·Series H·Attention… 은 단독으론 맞았으나 문맥에서 빠진 적이 있어 포함.
# 긴 패턴이 먼저 와야 한다.
SPOKEN = [
    ("Attention Is All You Need", "어텐션 이즈 올 유 니드"),
    ("Thinking Machines Lab", "씽킹 머신스 랩"),
    ("Thinking Machines", "씽킹 머신스"),
    ("DNNresearch", "디엔엔 리서치"),
    ("AMI Labs", "에이엠아이 랩스"),
    ("Series H", "시리즈 에이치"),
    ("LawZero", "로 제로"),
    ("Azure", "애저"),
    ("Cohere", "코히어"),
    ("SpaceXAI", "스페이스엑스에이아이"),
    ("xAI", "엑스에이아이"),
    ("ChatGPT", "챗지피티"),
    ("GPT-1", "지피티 원"),
    ("GPT-3", "지피티 쓰리"),
    ("GPT", "지피티"),
    ("LSTM", "엘에스티엠"),
    ("ImageNet", "이미지넷"),
    ("CUDA", "쿠다"),
    ("RLHF", "알엘에이치에프"),
    ("Llama", "라마"),
    ("SSI", "에스에스아이"),
    ("(GAN)", ""),
    ("AI", "에이아이"),
    ("수츠케버", "수츠케 버"),
]


_DIG = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_COUNT = {1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉", 10: "열"}
_MONTH = {1: "일월", 2: "이월", 3: "삼월", 4: "사월", 5: "오월", 6: "유월", 7: "칠월", 8: "팔월", 9: "구월", 10: "시월", 11: "십일월", 12: "십이월"}


def _kor_small(n: int) -> str:
    """10000 미만 자리값 독음 (십·백·천 앞의 일은 생략)."""
    out = ""
    for val, unit in ((1000, "천"), (100, "백"), (10, "십"), (1, "")):
        d, n = divmod(n, val)
        if d:
            out += (_DIG[d] if d > 1 or not unit else "") + unit
    return out


def kor_num(n: int) -> str:
    """정수를 한국어 자리값 독음으로 (8520 → 팔천오백이십, 연도도 같은 규칙)."""
    if n < 10000:
        return _kor_small(n) or "일"
    man, rest = divmod(n, 10000)
    return kor_num(man) + "만" + (_kor_small(rest) if rest else "")


def numbers_to_spoken(s: str) -> str:
    """화면용 아라비아 숫자를 낭독용 한글 독음으로 바꾼다. 단위 규칙 순서를 지킨다."""
    s = re.sub(r"(\d[\d,]*)억", lambda m: kor_num(int(m.group(1).replace(",", ""))) + "억", s)
    s = re.sub(r"(\d[\d,]*)만", lambda m: kor_num(int(m.group(1).replace(",", ""))) + "만", s)
    s = re.sub(r"(\d{4})년", lambda m: kor_num(int(m.group(1))) + "년", s)
    s = re.sub(r"(\d+)년", lambda m: kor_num(int(m.group(1))) + "년", s)
    s = re.sub(r"(\d{1,2})월", lambda m: _MONTH.get(int(m.group(1)), m.group(0)), s)
    s = re.sub(r"(\d{1,2})일", lambda m: kor_num(int(m.group(1))) + "일", s)
    s = re.sub(r"(\d+)명", lambda m: _COUNT.get(int(m.group(1)), kor_num(int(m.group(1)))) + "명", s)
    s = re.sub(r"(\d+)개", lambda m: _COUNT.get(int(m.group(1)), kor_num(int(m.group(1)))) + "개", s)
    return s


def to_spoken(s: str) -> str:
    for a, b in SPOKEN:
        s = s.replace(a, b)
    return numbers_to_spoken(s)


def strip_tags(s: str) -> str:
    """<span class="hi"> 같은 강조 태그를 제거한다."""
    return TAG.sub("", s).strip()


def parse_scenes(html: str) -> list[dict]:
    try:
        body = html.split("const SCENES = [", 1)[1].split("\n];", 1)[0]
    except IndexError:
        sys.exit("SCENES 배열을 찾지 못했습니다. HTML 경로를 확인하세요.")

    years = re.findall(r"year:'([^']*)'", body)
    parts = re.findall(r"part:(\d+)", body)
    # lines:[ ... ] 블록을 장면 순서대로 수집
    line_blocks = re.findall(r"lines:\[(.*?)\n  \]", body, flags=re.S)

    if len(years) != len(line_blocks):
        sys.exit(
            f"장면 수가 맞지 않습니다. year={len(years)}, lines={len(line_blocks)}"
        )

    scenes = []
    for i, (year, block) in enumerate(zip(years, line_blocks), start=1):
        # lines 블록의 각 줄은 홑따옴표 문자열이어야 한다. 큰따옴표·백틱·주석이 섞이면 조용히 유실되므로 중단한다.
        for bl in (x.strip() for x in block.splitlines()):
            if bl and not re.fullmatch(r"'(?:[^'\\]|\\.)*',?", bl):
                sys.exit(f"{i}장 lines 블록에 홑따옴표 문자열이 아닌 줄이 있습니다: {bl[:60]}")
        raw = re.findall(r"'((?:[^'\\]|\\.)*)'", block)
        lines = [strip_tags(x.replace("\\'", "'")) for x in raw]
        lines = [x for x in lines if x]
        scenes.append(
            {
                "id": f"{i:02d}-scene",
                "label": f"{i}장 · {year}",
                "part": int(parts[i - 1]) if len(parts) == len(years) else 1,
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
    scenes = parse_scenes(html)
    m = re.search(r'<section id="closing"[^>]*>\s*<p class="quote">(.*?)</p>', html, flags=re.S)
    if m:
        # HTML 이 엔딩 문구의 원본 — <br> 는 공백으로
        quote = re.sub(r"\s+", " ", strip_tags(re.sub(r"<br\s*/?>", " ", m.group(1))))
    else:
        # 슬라이드형 페이지(AIStory.html)는 엔딩을 END_QUOTE 상수로 들고 있다 — 그쪽이 원본
        qm = re.search(r'const END_QUOTE = ("(?:[^"\\]|\\.)*");', html)
        if not qm:
            sys.exit("HTML 에서 #closing .quote 와 END_QUOTE 를 모두 찾지 못했습니다(엔딩 문구의 원본).")
        quote = re.sub(r"\s+", " ", json.loads(qm.group(1)))
    ENDING["lines"] = [quote]
    ENDING["id"] = f"{len(scenes) + 1:02d}-ending"   # 장 수에 맞춰 자동 결정(하드코딩 금지)
    items = [OPENING]
    prev_part = None
    for sc in scenes:
        pt = sc.pop("part", 1)
        if pt != prev_part:
            items.append({"id": f"part{pt}", "label": f"{pt}부 · {PART_NAME[pt]}", "lines": [PART_TEXT[pt]]})
            prev_part = pt
        items.append(sc)
    items.append(ENDING)

    for it in items:
        # OmniVoice 에 한 번에 넘길 문장. 줄 사이는 마침표 간격으로 자연스럽게 이어진다.
        display = " ".join(it["lines"])
        it["lines"] = [to_spoken(x) for x in it["lines"]]
        it["text"] = " ".join(it["lines"])
        it["chars"] = len(it["text"])
        if it["text"] != display:
            it["display_text"] = display   # 화면 문구 원문 — 자막 좌표(sync.json)는 이것을 기준으로 잡는다

    out = {
        "language": "ko",
        "title": "인공지능을 만든 사람들",
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
