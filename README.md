# AIStory · 인공지능을 만든 사람들

AI 연구를 발전시킨 인물과 공동 연구팀, 데이터와 계산 도구, 연구 조직의 변화를 따라가는 한국어 학습 자료입니다. 기술의 계보 10장과 회사·사람의 이야기 9장으로 구성합니다. 인물 이름을 외우기보다 연구가 해결한 문제와 남은 한계를 설명하는 데 초점을 둡니다.

## 현재 상태

- 화면: 19장 + 부 구분 2개 + 엔딩 + 크레딧, 총 23화면. 인트로는 별도입니다.
- 낭독 원고: 오프닝 + 부 구분 2개 + 19장 + 엔딩, 총 23클립입니다. 화면 수와 클립 수가 같은 것은 우연이며 크레딧에는 낭독이 없습니다.
- 2026-10-05 개정은 음성을 합성하지 않았습니다. 기존 `audio18/*.mp3`와 매니페스트를 보존했습니다.
- 개정 원고의 실제 낭독 시간은 미측정입니다. 이전 매니페스트의 2,002.6초를 개정본 길이로 표시하지 않습니다.
- 기존 매니페스트에는 원고·파일 연결을 입증할 해시가 없습니다. 변경 여부를 확정할 수 없는 클립도 **검증 대기**로 두며 재생하지 않습니다. 브라우저 TTS로 자동 대체하지 않습니다.
- 실제 브라우저 렌더링 검증은 실행 환경의 Chromium 소켓 제한으로 미완료입니다. 코드·원고·정합성 테스트 결과와 구분해 [검토 보고서](review/2026-10-05-qa-report.md)에 기록합니다.

## 원본과 산출물

| 파일 | 역할 |
|---|---|
| `build_aistory.py` | 화면용 원고·인물·장별 시각 자료·확인 질문의 정본 |
| `slide.template.html` | 화면 구조·스타일·키보드 조작·오디오 상태 제어 |
| `extract_narration.py` | 정본을 낭독용 표기로 변환, 내장 JSON 추출, 오디오 정합성 판정 |
| `AIStory.html` | 빌드한 학습 페이지. 직접 편집하지 않음 |
| `AIStory-slide.html` | 같은 페이지의 호환 별칭. 빌드 산출물 |
| `narration.json` | 화면 원문과 낭독용 원고를 함께 담은 파생 파일 |
| `narration-export/` | 렌더링 인계용 텍스트·발음표·MP3 매핑·해시·안내 |
| `SOURCES.md` | 장별 근거, 확인 날짜, 확인 범위와 한계 |
| `LEARNING_GUIDE.md` | 학습 목표와 19장 확인 질문 |
| `review/verified_sources.json` | 출처 확인 상태를 구분한 구조화 기록 |

`narration.json`의 `lines`는 낭독용 표기입니다. `text`, `chars`, 해시는 이 필드에서 파생됩니다. 화면 원문은 `display_lines`와 `display_text`에 따로 보존합니다. 원고를 고칠 때는 `build_aistory.py`를 수정하고 다시 빌드합니다.

## 빌드와 음성 없는 검증

Python 3.10 이상과 Node 18 이상이 필요합니다. 아래 과정에는 모델 설치·다운로드·TTS 실행이 없습니다.

```bash
python build_aistory.py
python extract_narration.py AIStory.html -o narration.json
python tools/export_narration.py --verify-html
python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/test_slide_player.mjs
python tools/export_narration.py --check --verify-html
git diff --check
```

`python tools/check_project.py`는 위의 비음성 검사를 한 번에 실행하고 생성물 최신 여부를 검사합니다. 빌드 산출물이 오래되면 먼저 위의 빌드·내보내기를 실행하세요. `build_slide.py`는 정본에서 슬라이드 별칭을 생성하는 호환 명령이며 HTML을 원본으로 다시 추출하지 않습니다.

## 읽는 방법

HTTP 정적 서버로 `AIStory.html`을 열거나 파일을 직접 엽니다. 운영 환경에서 로컬 서버를 사용할 수 있다면 다음 명령으로 확인할 수 있습니다.

```bash
python -m http.server 8000
```

브라우저에서 `http://localhost:8000/AIStory.html`을 엽니다. 현재 개정본은 인트로의 **직접 넘기기**로 읽습니다. 각 장에서 인물 카드를 펼치거나 **대본**을 열어 전체 원고와 확인 질문을 볼 수 있습니다. 질문의 답은 펼쳐서 확인합니다. 화살표 키로 장을 넘기고, 대본 안에서는 Escape로 닫습니다. 시스템의 동작 줄이기 설정에서는 크레딧을 자동으로 움직이지 않습니다.

## 나중에 음성을 렌더링할 때

이번 개정의 범위에는 음성 생성이 포함되지 않습니다. 향후 별도로 승인된 렌더링은 `narration-export/RENDER_GUIDE.md`를 기준으로 진행합니다.

- 사용 권한이 있는 동일 참조 음성과 고정 설정을 사용합니다.
- 새 출력 폴더에서 만들고 기존 자산을 덮어쓰기 전에 전체 음성을 검토합니다.
- 원고 `text_sha256`와 최종 MP3 `audio_sha256`를 함께 기록합니다.
- 실제 길이, 잘림·무음·음량, 이름과 숫자의 독음, 자막을 확인합니다.
- 음질 검토가 끝난 클립만 매니페스트의 `quality_status`를 `approved`로 바꿉니다. 렌더러는 자동 승인하지 않습니다.
- 검증한 파일을 배치하고 다시 빌드해야 페이지의 오디오 상태가 갱신됩니다.

`render_tts.py` 등 기존 합성 도구는 남겨 두었습니다. `render_fix*.py`, `render_delta.py`, `review/splice_build.py`는 과거 편집·부분 렌더 작업 기록입니다. 현재 정본에 재실행하면 이전 원고를 되살릴 수 있으므로 현재 제작 절차에 사용하지 않습니다.
