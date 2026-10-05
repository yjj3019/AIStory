#!/usr/bin/env python3
"""Export a deterministic narration handoff. Never synthesize or modify audio."""

import argparse
import csv
import hashlib
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extract_narration import (SPOKEN, audio_status, json_text, narration_from_html,
                               narration_from_source, validate_narration)


RENDER_GUIDE = """# AIStory 음성 렌더 인계

## 현재 상태

이 묶음은 build_aistory.py의 원고에서 생성했습니다. 내보내기 과정에서는 TTS를 실행하지 않고 audio18/ 파일도 바꾸지 않습니다.
새 원고의 실측 총길이는 전 클립 렌더와 길이 검증을 마친 뒤 기록합니다. mp3-map.json의 existing_audio_seconds는 기존 manifest에 기록된 과거 길이입니다. 새 원고의 예상 시간이나 실측 시간으로 사용하지 않습니다.

status가 pending이면 현재 원고와 오디오의 일치를 입증하지 못한 상태입니다. 기존 파일이 있어도 그대로 배포하지 않습니다. verified는 원문 또는 문구 해시와 실제 MP3 바이트 해시가 모두 일치하고, quality_status가 approved인 상태입니다. 이 내보내기 도구가 음질을 자동 심사하는 것은 아닙니다. 렌더 담당자가 별도 검증을 끝낸 뒤 승인한 기록을 읽습니다. WAV용 .sha1 사이드카만으로 MP3 일치를 판정하지 않습니다.

## 원고 재생성 및 검증

저장소 루트에서 Python 3.10 이상으로 실행합니다. 아래 명령은 음성을 합성하지 않습니다.

```bash
python build_aistory.py
python extract_narration.py AIStory.html -o narration.json
python tools/export_narration.py --verify-html
python -m unittest discover -s tests -v
python tools/export_narration.py --check --verify-html
(cd narration-export && sha256sum -c SHA256SUMS)
```

원고를 고칠 때는 build_aistory.py의 데이터를 수정합니다. narration.json의 text와 chars는 lines에서 계산한 값이므로 직접 수정하지 않습니다. 발음 치환은 extract_narration.py의 확인된 목록을 사용합니다. 새 치환은 실제 오독을 확인한 뒤 추가합니다.

## 렌더 담당자가 별도 승인 후 진행할 순서

1. narration.json과 SHA256SUMS를 먼저 확인합니다. mp3-map.csv의 순서와 파일명이 웹페이지의 클립 순서입니다.
2. 기존에 승인된 목소리 캐시를 보존합니다. 참조 음성은 사용 권한이 있는 파일만 사용하고, --num-step 32를 유지합니다. --refresh-prompt나 --reuse로 검증을 우회하지 않습니다.
3. 디스크 여유와 모델·GPU 환경을 확인합니다. 다음 명령은 렌더 대상만 출력합니다.

```bash
python render_tts.py --narration narration-export/narration.json --out-dir audio18 --dry-run
```

4. 실제 합성은 별도 승인을 받은 환경에서 실행합니다. 아래 예시의 경로와 참조 전사는 승인된 값으로 바꿉니다. 이 문서 작성 과정에서는 실행하지 않았습니다.

```bash
python render_tts.py --narration narration-export/narration.json \\
  --out-dir audio18 --ref-audio ref/narrator.wav \\
  --ref-text "<승인된 참조 음성의 정확한 전사>" \\
  --prompt-cache voice_prompt.pt --speed 0.94 --num-step 32 --mp3
```

5. 최종 MP3를 전부 디코드해 길이·자/초·긴 무음·클리핑·음량을 검증합니다. STANDARDS.md의 음량 기준과 tools/verify/README.md의 절차를 따릅니다. 표본 청취만으로 전량 통과를 선언하지 않습니다.
6. 발음, 문장 누락, 목소리·속도의 일관성을 듣고 확인합니다. 오디오를 바꾼 클립의 자막 앵커도 다시 만듭니다. 기존 sync.json을 새 원고에 재사용하지 않습니다.
7. manifest에 각 클립의 text와 text_sha256, 최종 MP3 바이트의 audio_sha256, 실측 seconds를 기록합니다. 렌더 직후 quality_status는 pending_review입니다. 5~6단계의 전량 검증을 완료한 클립만 approved로 바꿉니다. 문구 해시를 현재 원고 값으로 덮어써서 기존 오디오를 새것으로 표시하면 안 됩니다. 음량 보정 등으로 MP3 바이트를 바꾸면 해시와 검증 기록도 다시 확인합니다.
8. build_aistory.py와 내보내기를 다시 실행합니다. status, rendered_seconds, 전 클립 총길이를 확인하고 웹페이지에서 재생·이동·정지를 점검합니다.

## 파일 구성

- narration.json: 렌더 입력. 화면용 display_lines와 낭독용 lines, 파생 text·chars·SHA256 포함
- narration.txt: 클립 ID·라벨을 붙인 낭독 원고
- readthrough.txt: 제목이나 파일명 없이 이어 읽는 낭독 원고
- pronunciation.md: 기존 확인된 발음 치환과 숫자 처리 범위
- mp3-map.json / mp3-map.csv: 재생 순서·파일명·문구 해시·오디오 검증 상태
- bundle-manifest.json: 입력 파일 해시와 묶음의 상태·수량
- SHA256SUMS: 자기 자신을 제외한 산출물의 바이트 해시

생성 시각이나 절대 경로는 넣지 않습니다. 같은 입력 파일과 오디오 검증 근거로 내보내면 산출물 바이트가 같습니다. --check는 파일을 쓰지 않고 누락·변경을 검사합니다.
"""


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_bundle(narration: dict, root: pathlib.Path) -> dict[str, bytes]:
    """Pure artifact construction, apart from read-only input/audio evidence."""
    validate_narration(narration)
    root = pathlib.Path(root)
    states = audio_status(narration, root)
    files: dict[str, bytes] = {}

    def add(name: str, text: str) -> None:
        files[name] = text.replace("\r\n", "\n").encode("utf-8")

    add("narration.json", json_text(narration))
    add("narration.txt", "\n\n".join(
        f"[{item['id']}] {item['label']}\n" + "\n\n".join(item["lines"])
        for item in narration["items"]) + "\n")
    add("readthrough.txt", "\n\n".join(
        line for item in narration["items"] for line in item["lines"]) + "\n")
    pronunciation = ["# 낭독 표기 확인표", "",
                     "화면 원고는 그대로 보존하고 낭독 입력에만 아래 치환을 적용합니다.",
                     "기존 저장소에서 확인된 목록을 유지했습니다. 이 내보내기에서는 새 음성을 합성하거나 발음을 다시 청취하지 않았습니다.", "",
                     "| 화면 표기 | 낭독 표기 | 해당 클립 |", "|---|---|---|"]
    for original, replacement in SPOKEN:
        ids = [item["id"] for item in narration["items"] if any(original in line for line in item["display_lines"])]
        pronunciation.append(f"| {original} | {replacement or '(괄호 표기 생략)'} | {', '.join(ids) or '현재 원고에 없음'} |")
    pronunciation.extend(["", "## 숫자", "",
                          "연도·억·만은 자리값으로 읽습니다. 0은 영, 소수점 아래는 한 자리씩 읽습니다. 억·조 자리값을 반복된 만으로 바꾸지 않습니다.",
                          "6월과 10월은 유월·시월입니다. 5일 동안처럼 기간이 분명한 표현은 닷새 동안으로 바꿉니다.",
                          "명·개·건 앞의 1~99는 한·두·열한·스무·스물한과 같은 고유어 수사를 사용합니다. 단위가 없거나 뜻이 불명확한 숫자는 그대로 둡니다.",
                          "숫자 정규화는 텍스트 규칙 테스트를 통과한 범위입니다. 실제 TTS 청취 검증은 렌더 후 진행합니다.", ""])
    add("pronunciation.md", "\n".join(pronunciation))
    rows = []
    for order, item in enumerate(narration["items"], 1):
        rows.append({"order": order, "id": item["id"], "label": item["label"],
                     "chars": item["chars"], **states[item["id"]]})
    all_verified = all(row["status"] == "verified" and row["rendered_seconds"] is not None for row in rows)
    past_seconds = [row["existing_audio_seconds"] for row in rows if row["existing_audio_seconds"] is not None]
    current_total = round(sum(row["rendered_seconds"] for row in rows), 3) if all_verified else None
    mapping = {"schema_version": 1, "duration_note": "existing_audio_seconds is historical manifest metadata, not the new script runtime",
               "current_script_rendered_total_seconds": current_total,
               "existing_audio_recorded_total_seconds": round(sum(past_seconds), 3) if past_seconds else None,
               "items": rows}
    add("mp3-map.json", json_text(mapping))
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    add("mp3-map.csv", csv_buffer.getvalue())
    input_hashes = {}
    for name in ("build_aistory.py", "extract_narration.py", "tools/export_narration.py", "slide.template.html", "render_tts.py", "audio18/manifest.json"):
        path = root / name
        if path.is_file():
            input_hashes[name] = _sha_bytes(path.read_bytes())
    add("bundle-manifest.json", json_text({
        "schema_version": 1,
        "canonical_source": "build_aistory.py",
        "generated_by": "python tools/export_narration.py",
        "audio_rendered_by_export": False,
        "clip_count": len(rows),
        "spoken_character_count": sum(item["chars"] for item in narration["items"]),
        "pending_clip_count": sum(row["status"] == "pending" for row in rows),
        "verified_clip_count": sum(row["status"] == "verified" for row in rows),
        "current_script_rendered_total_seconds": current_total,
        "input_sha256": input_hashes,
    }))
    add("RENDER_GUIDE.md", RENDER_GUIDE)
    add("SHA256SUMS", "".join(f"{_sha_bytes(files[name])}  {name}\n" for name in sorted(files)))
    return files


def write_bundle(files: dict[str, bytes], output: pathlib.Path, *, check: bool = False) -> list[str]:
    """Check is strictly read-only. Return missing/different relative names."""
    changed = []
    if not check:
        output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = output / name
        if not path.is_file() or path.read_bytes() != content:
            changed.append(name)
            if not check:
                path.write_bytes(content)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "narration-export")
    parser.add_argument("--check", action="store_true", help="Fail if checked-in exports are missing or stale; never write")
    parser.add_argument("--verify-html", action="store_true", help="Require both generated HTML pages to contain the same NARRATION")
    args = parser.parse_args()
    import build_aistory
    try:
        narration = narration_from_source(build_aistory)
        if args.verify_html:
            for name in ("AIStory.html", "AIStory-slide.html"):
                embedded = narration_from_html((ROOT / name).read_text(encoding="utf-8"))
                if embedded != narration:
                    raise ValueError(f"{name}: embedded narration differs from canonical source; rebuild first")
        changed = write_bundle(make_bundle(narration, ROOT), args.out, check=args.check)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    if args.check and changed:
        parser.exit(1, "Stale or missing exports: " + ", ".join(changed) + "\n")
    print(f"{'Verified' if args.check else 'Exported'} {len(narration['items'])} clips to {args.out}; no audio rendered")


if __name__ == "__main__":
    main()
