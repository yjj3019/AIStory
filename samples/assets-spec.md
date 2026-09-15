# 자산 스펙 (실제 파일은 저장소에 없음)

실제 이미지·오디오 자산은 저작권/용량 문제로 이 저장소에 포함하지 않는다.
아래는 파이프라인이 기대하는 파일 규격·네이밍 규칙만 기록한 문서다.

## portraits/ (인물 사진)

- 경로: `portraits/<person-id>.jpg` — `person-id`는 SCENES의 `who[]`, `P` 데이터의 키와 동일해야 함
- 실측 예시 규격: 폭 500px 고정, 세로는 원본 비율(인물 바스트샷, 정방형~세로 비율 혼재)
- 용도: 클릭형 인물 카드(`wireMap()`)에서 인물 클릭 시 표시

## context-images/ (장면 배경 이미지)

- 경로: `context-images/<slug>.jpg` — `slug`는 SCENES 각 장면의 `contextImg.src` 파일명과 동일
- 실측 예시 규격: 폭 1600px 내외, 가로형(장소·사물 사진)
- 용도: 각 장면 진입 시 배경/컨텍스트 이미지로 표시

## ref/ (TTS 참조 음성)

- 경로: `ref/narrator.wav`
- 용도: `render_tts.py --ref-audio`로 voice cloning 프롬프트 생성(1회 생성 후 `voice_prompt.pt`로 캐시, 전 클립 재사용)
- 요구사항: 참조 음성 발음을 그대로 옮긴 텍스트를 `--ref-text`로 함께 전달해야 함

## audio/ (렌더링된 내레이션)

- 경로: `audio/<id>.mp3` / `audio/<id>.wav`, `id`는 `00-opening` / `NN-scene`(2자리) / `16-ending`
- `audio/manifest.json`: 클립별 실측 길이(초). 구조 샘플은 `samples/audio-manifest.sample.json` 참고
- 웹페이지는 해당 id의 오디오 파일이 없으면 브라우저 내장 TTS로 자동 폴백한다(오디오 필수 아님)