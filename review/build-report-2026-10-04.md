# AIStory 신규 제작 빌드 리포트 (2026-10-04)

전제: 기존 본문 파일이 존재하지 않아, 저장소 파이프라인 코드와 PROGRESS.md 기록을 기준으로 18장 본문을 신규 제작함.

## 산출물 (AIStory_review/ 루트)

| 파일 | 내용 |
|---|---|
| `AIStory.html` | 신규 본문 페이지. SCENES 18장, 인물 49명 (P 46 + RIVALS 3), 인트로 게이트, 인물 카드, 인물 목록, 재생 플레이어 (audio18 파일 우선, 없으면 브라우저 음성 폴백) |
| `narration.json` | `extract_narration.py` 추출 결과. 20개 항목 (00-opening, 01~18-scene, 19-ending), 총 12,121자 |
| `AIStory-slide.html` | `build_slide.py` 생성 슬라이드형 페이지 |
| `build_aistory.py` | 조립 스크립트. 원고 데이터가 단일 원본, 재실행으로 HTML 재생성 |

## 반영 내용

- BotStory 스타일 전면 통일: 해요체, 숫자 한글 수사 전수 변환, 장 끝 메타 요약 폐지 (예고·한계 고지·지금 당신의 손에 3형 교체), 오프닝 8단계 골격과 엔딩 질문 콜백
- 사실 정정 3건 반영: SSI 그로스 이탈·수츠케버 CEO는 2025년, 셰이저는 OpenAI 복귀가 아닌 2026-06 신규 합류, OpenAI 상장 준비 공식 확인 2026-06-08
- 누락 보완 우선순위 상 7건 통합: 역전파 (베르보스·루멜하트), 섀넌, 튜링 확대, 구드펠로 GAN, 서튼, 앤드류 응·콜러, 젠슨 황 5장 배치. 중 항목 중 LSTM 다리 단락, 점퍼 알파폴드 공동 수상도 반영

## 검증 결과

| 항목 | 결과 |
|---|---|
| `extract_narration.py` 추출 | 20개 항목 정상, 총 12,121자 |
| `review/style_check.py` | BotStory 규격 통과 — 해요체 99.8% (합니다체는 엔딩 감사 1문장), 아라비아 숫자 0개, 70자 초과 문장 0개, 의문문 0.5% |
| 라틴 문자 잔류 스캔 | 없음 (전부 한글 음차) |
| 인물 키 무결성 | who 참조 49명 전원 P/RIVALS에 존재 (빌드 시 assert) |
| JS 문법 (node --check) | AIStory.html, AIStory-slide.html 모두 통과 |
| 예상 시간 | 12,121자 기준 약 35~38분 (기존 OmniVoice 실측 345자/분 및 추출기 320자/분 환산). 실측은 합성 후 확정 |

## 스타일 통일 후속 (같은 날)

- 사용자 요청으로 `AIStory.html`을 BotStory와 동일한 슬라이드 템플릿(`slide.template.html`)으로 재생성. `AIStory.html`과 `AIStory-slide.html`이 같은 파일 (64,992 bytes)
- 템플릿 오프닝 문구를 새 원고로 교체하고, 엔딩 사진 출처 문구·연도 표기를 사진 없는 제작본에 맞게 정정 (템플릿 원본에 반영)
- `extract_narration.py`에 END_QUOTE 폴백, `build_slide.py`에 END_QUOTE·ROLL_HTML 폴백을 추가해 슬라이드형 소스에서도 재추출·재생성이 되게 함. 재생성 결과 차이는 제목과 무해한 세미콜론 중복뿐
- 재검증: narration 텍스트 이전과 동일, style_check 통과, JS 문법 통과

## 장표 품질 보강 + 음성 렌더 준비 (같은 날 후속)

- 장표: 전 장에 핵심 숫자 통계 블록 추가 (17개 장), 비교표 4개 장 추가 (9장 LSTM vs 트랜스포머, 12장 오픈에이아이 vs 앤트로픽, 17장 2026 기업 지형, 18장 계보 밖 인물). 나레이션 텍스트 불변 재확인, JS 통과
- 음성: 이 환경에서는 렌더 불가 — OmniVoice·torch 없음, CPU 2코어·메모리 7GB, 동일 목소리 원본(`voice_prompt.pt`)이 rhel-storage와 사용 PC에만 있고 SSH도 차단됨. `render_tts.py --dry-run`으로 20클립 전량 생성 대상 확인 완료. rhel-storage에서 캐시 목소리로 실행 필요 (`--force`·`--refresh-prompt` 금지)

## 미검증·남은 것

- 음성 합성 미실시: rhel-storage에서 서버 캐시 `voice_prompt.pt`로 `render_tts.py` 실행 필요 (이 PC 렌더링 금지 규칙 유지). 합성 후 STT 검증과 `audio18/sync.json` 재생성 필요
- 실브라우저 재생·레이아웃 확인 미실시 (JS 문법과 데이터 무결성까지만 검증)
- 문장 평균 29.0자로 BotStory 실측 (33.1자)보다 다소 짧음. 호흡이 끊기는 느낌이면 문장 병합 조정 가능
- 인물 사진 없음: 이니셜 폴백 전제. 공개 시 사진은 Commons 자유 라이선스만 사용한다는 기존 원칙 유지
- GitHub 반영 미실시: `AIStory.html`·`narration.json`은 저장소 .gitignore 대상이라 커밋되지 않음. 로컬 파일로만 존재
