#!/usr/bin/env python3
"""Derive spoken scripts from build_aistory.py or its generated HTML, without TTS.

Canonical content lives in build_aistory.py. Generated HTML carries the same
NARRATION JSON. The legacy regex parser is opt-in and has no duplicate prose.
"""

import argparse
import ast
import hashlib
import html as html_lib
import json
import math
import pathlib
import re
import sys
from collections.abc import Mapping


def json_text(value) -> str:
    """Stable UTF-8 JSON representation used by builders and export tools."""
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


_DIG = ["영", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_COUNT = {1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉"}
_TENS = {1: "열", 2: "스물", 3: "서른", 4: "마흔", 5: "쉰", 6: "예순", 7: "일흔", 8: "여든", 9: "아흔"}
_MONTH = {1: "일월", 2: "이월", 3: "삼월", 4: "사월", 5: "오월", 6: "유월", 7: "칠월", 8: "팔월", 9: "구월", 10: "시월", 11: "십일월", 12: "십이월"}
_DAY = {1: "하루", 2: "이틀", 3: "사흘", 4: "나흘", 5: "닷새", 6: "엿새", 7: "이레", 8: "여드레", 9: "아흐레", 10: "열흘"}
_NUMBER = r"(?<![\d.,+\-])([+\-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?![\d.,])"
TAG = re.compile(r"<[^>]+>")


def _kor_small(n: int) -> str:
    """Read a nonnegative integer below 10,000."""
    if not 0 <= n < 10000:
        raise ValueError("_kor_small requires 0 <= n < 10000")
    out = ""
    for val, unit in ((1000, "천"), (100, "백"), (10, "십"), (1, "")):
        digit, n = divmod(n, val)
        if digit:
            out += (_DIG[digit] if digit > 1 or not unit else "") + unit
    return out


def kor_num(n: int) -> str:
    """Integer reading, including zero, negatives and 만/억/조 boundaries."""
    if not isinstance(n, int):
        raise TypeError("kor_num requires an integer")
    if n < 0:
        return "마이너스 " + kor_num(-n)
    if n == 0:
        return "영"
    groups = []
    for unit in ("", "만", "억", "조", "경", "해", "자", "양", "구", "간", "정"):
        n, group = divmod(n, 10000)
        if group:
            groups.append(_kor_small(group) + unit)
        if not n:
            return "".join(reversed(groups))
    raise ValueError("number exceeds supported Korean units")


def _read_number(value: str) -> str:
    value = value.replace(",", "")
    sign = "마이너스 " if value.startswith("-") else "플러스 " if value.startswith("+") else ""
    whole, dot, fraction = value.lstrip("+-").partition(".")
    return sign + kor_num(int(whole)) + ("점" + "".join(_DIG[int(c)] for c in fraction) if dot else "")


def _read_count(value: str) -> str:
    number = int(value.replace(",", ""))
    if number == 20:
        return "스무"
    if 0 < number < 100:
        tens, units = divmod(number, 10)
        return _TENS.get(tens, "") + _COUNT.get(units, "")
    return kor_num(number)


def numbers_to_spoken(s: str) -> str:
    """Read explicit units only; never silently reinterpret arbitrary digits."""
    s = re.sub(_NUMBER + r"(억|만|년)", lambda m: _read_number(m[1]) + m[2], s)
    # Dates and counters use integers, and cannot consume a decimal suffix.
    integer = r"(?<![\d.,+\-])(\d+)(?![\d.,])"
    s = re.sub(integer + r"월", lambda m: _MONTH.get(int(m[1]), m[0]), s)
    s = re.sub(integer + r"일(?= 만에| 동안|째|의)", lambda m: _DAY.get(int(m[1]), kor_num(int(m[1])) + "일"), s)
    s = re.sub(integer + r"일", lambda m: kor_num(int(m[1])) + "일", s)
    counter = r"(?<![\d.,+\-])(\d{1,3}(?:,\d{3})+|\d+)(?![\d.,])"
    s = re.sub(counter + r"명", lambda m: _read_count(m[1]) + "명", s)
    s = re.sub(counter + r"(개|건)", lambda m: _read_count(m[1]) + " " + m[2], s)
    return s


def to_spoken(s: str) -> str:
    for source, spoken in SPOKEN:
        s = s.replace(source, spoken)
    return numbers_to_spoken(s)


def strip_tags(s: str) -> str:
    return html_lib.unescape(TAG.sub("", re.sub(r"<br\s*/?>", " ", s))).strip()


def _make_item(clip_id: str, label: str, lines: list[str]) -> dict:
    display_lines = [strip_tags(line) for line in lines]
    if not display_lines or any(not line for line in display_lines):
        raise ValueError(f"{clip_id}: empty narration line")
    spoken_lines = [to_spoken(line) for line in display_lines]
    text = " ".join(spoken_lines)
    return {"id": clip_id, "label": label, "display_lines": display_lines,
            "lines": spoken_lines, "text": text, "chars": len(text),
            "display_text": " ".join(display_lines), "text_sha256": text_sha256(text)}


def narration_from_source(source) -> dict:
    """Build from a module or globals mapping, without importing/running a build."""
    values = source if isinstance(source, Mapping) else vars(source)
    chapters = values["CHAPTERS"]
    parts = values["PART_OF"]
    if not chapters or len(chapters) != len(parts):
        raise ValueError("CHAPTERS and PART_OF must have the same nonzero length")
    items = [_make_item("00-opening", "오프닝", values["OPENING_PARAS"])]
    prev_part = None
    seen_parts = set()
    for index, (chapter, part) in enumerate(zip(chapters, parts), 1):
        year, _title, _who, lines = chapter
        if part != prev_part:
            if part in seen_parts:
                raise ValueError(f"part {part} is not contiguous")
            seen_parts.add(part)
            name = values["PART_INFO"][part]["name"]
            items.append(_make_item(f"part{part}", f"{part}부 · {name}", [values["PART_TEXT"][part]]))
            prev_part = part
        items.append(_make_item(f"{index:02d}-scene", f"{index}장 · {year}", lines))
    items.append(_make_item(f"{len(chapters) + 1:02d}-ending", "엔딩", [values["ENDING_TEXT"]]))
    result = {"language": "ko", "title": "인공지능을 만든 사람들", "items": items}
    validate_narration(result)
    return result


def validate_narration(narration: dict) -> None:
    items = narration.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("narration.items must be a nonempty list")
    ids = set()
    for item in items:
        clip_id = item.get("id", "")
        if not isinstance(clip_id, str) or not re.fullmatch(r"(?:\d{2,}-(?:opening|scene|ending)|part[1-9]\d*)", clip_id) or clip_id in ids:
            raise ValueError(f"invalid or duplicate clip id: {clip_id}")
        ids.add(clip_id)
        lines = item.get("lines")
        if not isinstance(lines, list) or not lines or any(not isinstance(line, str) or not line.strip() for line in lines):
            raise ValueError(f"{clip_id}: invalid lines")
        text = " ".join(lines)
        if item.get("text") != text or item.get("chars") != len(text):
            raise ValueError(f"{clip_id}: text/chars do not derive from lines")
        if item.get("text_sha256") != text_sha256(text):
            raise ValueError(f"{clip_id}: text_sha256 mismatch")
        display_lines = item.get("display_lines")
        if (not isinstance(display_lines, list) or not display_lines
                or any(not isinstance(line, str) for line in display_lines)
                or item.get("display_text") != " ".join(display_lines)
                or lines != [to_spoken(line) for line in display_lines]):
            raise ValueError(f"{clip_id}: display and spoken lines disagree")


def _js_value(html: str, name: str):
    match = re.search(r"\bconst\s+" + re.escape(name) + r"\s*=\s*", html)
    if not match:
        raise ValueError(f"HTML has no {name}; rebuild with build_aistory.py")
    tail = html[match.end():]
    try:
        return json.JSONDecoder().raw_decode(tail)[0]
    except json.JSONDecodeError:
        # Legacy generated scripts used Python-compatible single-quoted strings.
        quoted = re.match(r"'(?:[^'\\]|\\.)*'", tail)
        if quoted:
            return ast.literal_eval(quoted[0])
        raise ValueError(f"{name} must contain literal JSON") from None


def parse_scenes(html: str) -> list[dict]:
    """Strict legacy SCENES parser; preserved for migration and cross-checking."""
    match = re.search(r"const\s+SCENES\s*=\s*\[(.*?)\n\];", html, re.S)
    if not match:
        raise ValueError("SCENES array not found")
    body = match[1]
    years = re.findall(r"year:\s*('(?:[^'\\]|\\.)*')", body)
    parts = re.findall(r"part:\s*(\d+)", body)
    blocks = re.findall(r"lines:\s*\[(.*?)\n\s*\]", body, re.S)
    if not years or len(years) != len(blocks) or len(parts) != len(years):
        raise ValueError(f"SCENES lengths disagree: year={len(years)}, lines={len(blocks)}, part={len(parts)}")
    scenes = []
    for index, (year, block, part) in enumerate(zip(years, blocks, parts), 1):
        raw_lines = [line.strip() for line in block.splitlines() if line.strip()]
        if any(not re.fullmatch(r"'(?:[^'\\]|\\.)*',?", line) for line in raw_lines):
            raise ValueError(f"scene {index}: unsupported legacy string syntax")
        lines = [strip_tags(ast.literal_eval(line.rstrip(","))) for line in raw_lines]
        scenes.append({"id": f"{index:02d}-scene", "label": f"{index}장 · {ast.literal_eval(year)}", "part": int(part), "lines": lines})
    return scenes


def narration_from_html(html: str, *, legacy: bool = False) -> dict:
    """Read canonical embedded JSON; old markup requires explicit --legacy-html."""
    if re.search(r"\bconst\s+NARRATION\s*=", html):
        result = _js_value(html, "NARRATION")
        validate_narration(result)
        return result
    if not legacy:
        raise ValueError("HTML has no NARRATION JSON. Rebuild, or use --legacy-html for migration.")
    scenes = parse_scenes(html)
    part_info = _js_value(html, "PARTS")
    part_text = _js_value(html, "PART_TEXT")
    items = [_make_item("00-opening", "오프닝", [_js_value(html, "OPENING_TEXT")])]
    previous = None
    for scene in scenes:
        part = scene["part"]
        if part != previous:
            items.append(_make_item(f"part{part}", f"{part}부 · {part_info[str(part)]['name']}", [part_text[str(part)]]))
            previous = part
        items.append(_make_item(scene["id"], scene["label"], scene["lines"]))
    items.append(_make_item(f"{len(scenes) + 1:02d}-ending", "엔딩", [_js_value(html, "END_QUOTE")]))
    result = {"language": "ko", "title": "인공지능을 만든 사람들", "items": items}
    validate_narration(result)
    return result


def audio_status(narration: dict, root: pathlib.Path) -> dict:
    """Read-only freshness evidence. Historical duration alone proves nothing.

    SHA1 sidecars describe WAV input, not the MP3, so do not establish MP3
    freshness on their own. Manifest script evidence and audio SHA256 must
    both match. Playback also requires an explicit approved quality review;
    this function reads that decision and does not perform acoustic QA.
    """
    root = pathlib.Path(root)
    manifest_path = root / "audio18" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest.get("items", [])
        if not isinstance(entries, list):
            raise ValueError("manifest items must be a list")
        by_id = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or entry["id"] in by_id:
                raise ValueError("invalid or duplicate manifest id")
            by_id[entry["id"]] = entry
        manifest_error = None
    except (OSError, ValueError, TypeError, AttributeError):
        by_id = {}
        manifest_error = "manifest_missing_or_invalid"
    result = {}
    for item in narration["items"]:
        clip_id, text = item["id"], item["text"]
        expected_mp3 = f"audio18/{clip_id}.mp3"
        path = root / expected_mp3
        exists = path.is_file() and path.stat().st_size > 0
        actual_audio_sha256 = hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
        entry = by_id.get(clip_id, {})
        duration = entry.get("seconds")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            duration = None
        evidence = []
        if "text" in entry:
            evidence.append(entry["text"] == text)
        if "text_sha1" in entry:
            evidence.append(entry["text_sha1"] == hashlib.sha1(text.encode("utf-8")).hexdigest())
        if "text_sha256" in entry:
            evidence.append(entry["text_sha256"] == text_sha256(text))
        file_matches = entry.get("file", f"{clip_id}.mp3") == f"{clip_id}.mp3"
        strong_script_evidence = "text" in entry or "text_sha256" in entry
        script_verified = strong_script_evidence and bool(evidence) and all(evidence)
        audio_verified = exists and file_matches and entry.get("audio_sha256") == actual_audio_sha256
        quality_status = entry.get("quality_status", "unreviewed")
        if not isinstance(quality_status, str) or quality_status not in {"unreviewed", "pending_review", "approved", "rejected"}:
            quality_status = "unreviewed"
        verified = script_verified and audio_verified and quality_status == "approved"
        if not exists:
            reason = "audio_missing"
        elif manifest_error:
            reason = manifest_error
        elif not file_matches:
            reason = "manifest_file_mismatch"
        elif not strong_script_evidence:
            reason = "no_recorded_text_or_sha256"
        elif not script_verified:
            reason = "script_changed_or_conflicting_evidence"
        elif not entry.get("audio_sha256"):
            reason = "no_recorded_audio_hash"
        elif not audio_verified:
            reason = "audio_hash_mismatch"
        elif quality_status != "approved":
            reason = "quality_review_not_approved"
        else:
            reason = "script_audio_and_quality_verified"
        result[clip_id] = {"status": "verified" if verified else "pending",
                           "text_sha256": text_sha256(text), "expected_mp3": expected_mp3,
                           "existing_audio_sha256": actual_audio_sha256,
                           "script_verified": script_verified, "audio_verified": audio_verified,
                           "quality_status": quality_status,
                           "existing_audio_seconds": duration,
                           "rendered_seconds": duration if verified else None,
                           "reason": reason}
    return result


def main() -> None:
    # Keep Windows terminals UTF-8, without mutating stdout when imported.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Canonical source / generated HTML → narration JSON (no TTS)")
    parser.add_argument("html", nargs="?", help="Generated HTML; omit to read build_aistory.py")
    parser.add_argument("-o", "--output", default="narration.json")
    parser.add_argument("--legacy-html", action="store_true", help="Explicitly parse older generated HTML")
    args = parser.parse_args()
    try:
        if args.html:
            narration = narration_from_html(pathlib.Path(args.html).read_text(encoding="utf-8"), legacy=args.legacy_html)
        else:
            import build_aistory
            narration = narration_from_source(build_aistory)
        pathlib.Path(args.output).write_text(json_text(narration), encoding="utf-8", newline="\n")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    total = sum(item["chars"] for item in narration["items"])
    print(f"{len(narration['items'])}개 항목, 총 {total}자 → {args.output}")
    print("새 원고의 낭독 시간은 음성 렌더 후에만 실측할 수 있습니다.")


if __name__ == "__main__":
    main()
