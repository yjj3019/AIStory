# -*- coding: utf-8 -*-
"""new_data.py 의 원고·인물·화면 데이터를 build_aistory.py 에 반영한다. 단계마다 앵커를 검증한다."""
import importlib.util, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("nd", ROOT / "review" / "new_data.py")
nd = importlib.util.module_from_spec(spec); spec.loader.exec_module(nd)

p = ROOT / "build_aistory.py"
src = p.read_text(encoding="utf-8")

def fmt_chapter(ch):
    year, title, who, lines = ch
    ls = ",\n".join(' "' + l + '"' for l in lines)
    return f'("{year}", "{title}", {who!r}, [\n{ls},\n])'

def check(cond, msg):
    if not cond:
        sys.exit("앵커 검증 실패: " + msg)

# 1) OPENING_PARAS 교체
new_opening = "OPENING_PARAS = [\n" + ",\n".join('    "' + t + '"' for t in nd.OPENING_PARAS) + ",\n]"
src2, n = re.subn(r"OPENING_PARAS = \[.*?\n\]", new_opening, src, count=1, flags=re.S)
check(n == 1, "OPENING_PARAS"); src = src2

# 2) CHAPTERS 교체 (CHAPTERS = [ ... CHAPTERS += [ ... ]) → 단일 블록
i0 = src.index("CHAPTERS = [")
i1 = src.index("# 인물 데이터")
new_ch = "CHAPTERS = [\n" + ",\n".join(fmt_chapter(c) for c in nd.CHAPTERS) + ",\n]\n\n"
src = src[:i0] + new_ch + src[i1:]

# 3) PART 상수 추가 (CHAPTERS 뒤)
anchor = "# 인물 데이터"
part_block = ("PART_INFO = " + repr(nd.PART_INFO) + "\n"
              "PART_TEXT = " + repr(nd.PART_TEXT) + "\n"
              "PART_OF = " + repr(nd.PART_OF) + "   # 장 번호(1부터) → 부\n\n")
src = src.replace(anchor, part_block + anchor, 1)

# 4) 신규 인물 삽입 (P 닫기 직전)
ins = "".join(f' "{k}": {v!r},\n' for k, v in nd.NEW_PEOPLE.items())
old_close = '"wang": {"n":"알렉산더 왕"'
j = src.index(old_close)
jend = src.index("},\n}", j) + len("},\n")
src = src[:jend] + ins + src[jend:]

# 5) 인물 수정 (정확 문자열 치환)
edits = [
 ('"t":["강화학습 교과서","2019 비터 레슨"]', '"t":["강화학습 교과서","2019 비터 레슨","2024 튜링상"]', 1),
 ('"t":["1986 역전파 대중화","2012 알렉스넷 지도","2018 튜링상"]', '"t":["1986 역전파 대중화","2012 알렉스넷 지도","2018 튜링상","2024 노벨 물리학상"]', 1),
 ('"e":"앤트로픽으로 이적 (2026)","t":["알파폴드 개발","2024 노벨 화학상","2026 앤트로픽 이적"]', '"e":"앤트로픽 합류 (2026)","t":["알파폴드 개발","2024 노벨 화학상","2026 앤트로픽 합류 발표"]', 1),
 ('"e":"당시 오픈에이아이 연구자","t":["2020 지피티 쓰리 주저자"]', '"e":"앤트로픽 공동 창업자","t":["2020 GPT-3 주저자","앤트로픽 공동 설립"]', 1),
 ('"karpathy": {"n":"안드레이 카파시","m":"카파시","e":"앤트로픽 (2026 합류)","t":["2026 앤트로픽 합류"]', '"karpathy": {"n":"안드레이 카파시","m":"카파시","e":"앤트로픽 (2026 합류)","t":["오픈에이아이 창립 멤버","2026 앤트로픽 합류"]', 1),
 ('"t":["1997 엘에스티엠 공저"]', '"t":["1997 LSTM 공저"]', 2),
 ('"t":["2018 지피티 원 주저자"]', '"t":["2018 GPT-1 주저자"]', 1),
 ('"why":"유럽에서 열린 모델의 길을 연 사람 중 하나예요"', '"why":"유럽에서 오픈 웨이트의 길을 연 사람 중 하나예요"', 1),
 ('"why":"열린 모델의 길을 연 사람 중 하나예요"', '"why":"오픈 웨이트의 길을 연 사람 중 하나예요"', 1),
]
for old, new, cnt in edits:
    c = src.count(old)
    check(c == cnt, f"인물 수정 앵커 {old[:30]} (발견 {c}, 기대 {cnt})")
    src = src.replace(old, new)

# 6) CHAPTER_VISUALS 교체
i0 = src.index("CHAPTER_VISUALS = {")
i1 = src.index("def js_str")
new_vis = "CHAPTER_VISUALS = " + repr(nd.CHAPTER_VISUALS) + "\n\n"
src = src[:i0] + new_vis + src[i1:]

p.write_text(src, encoding="utf-8", newline="\n")
print("반영 완료:", len(src), "bytes")
