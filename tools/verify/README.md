# tools/verify — 렌더 결과 검증 도구

콘텐츠(대본·오디오·사진)는 저장소에 없고, 이 폴더의 스크립트는 **콘텐츠를 포함하지 않는다.** 오디오를 다시 렌더한 뒤 품질을 확인할 때 쓴다.
프로젝트 루트(`AIStory.html`, `narration.json`, `audio18/`가 있는 곳)에서 실행한다.

| 스크립트 | 용도 |
|---|---|
| `sim_audio.py` | `audio18/` 정합성: 파일 세트, 문구 해시, wav·mp3·manifest 길이, 속도 이상치, 무음·클리핑 |
| `sim_page.mjs` | 실제 Chrome(헤드리스)으로 두 페이지를 띄워 클립 id·길이·타이머·재생·콘솔 오류 확인 |
| `stt_check.py` | faster-whisper로 낭독을 받아써 대본과 비교(`stt_report.md`), 자막 앵커 `audio_sync.json`(→ `audio18/sync.json`)과 청취 목록 생성 |
| `cross_stt.py` | 의심 구간을 모델 2종 x (힌트 없음/있음)으로 교차 확인 |
| `scan_slides.mjs` | 슬라이드 인물 칸이 내용 때문에 넘치는지 전수 측정(해상도 3종) |
| `probe_roll.mjs` | 엔딩 크레딧 자동 스크롤 동작 측정(동작 줄이기 켬/끔) |
| `shot.mjs` | 페이지 스크린샷 + 레이아웃 수치 |

## 준비
- `ffmpeg`/`ffprobe`, Chrome, Node 22+ (내장 `WebSocket` 사용), Python 3.10+.
- STT: `pip install faster-whisper jiwer` 후 모델을 `~/whisper-models/large-v3`(필요하면 `large-v3-turbo`)에 둔다.
  사내 프록시 환경에서는 Python 다운로더가 인증서로 실패할 수 있어 `curl -x <프록시>`로 `model.bin` 등을 받는다.
- 웹 서버: 프로젝트 루트에서 `python -m http.server <빈 포트>`를 띄우고 `sim_page.mjs`/`scan_slides.mjs`/`shot.mjs`에 URL을 준다.

## 예
```bash
python tools/verify/sim_audio.py --root . --audio audio18 --narration narration.json
python tools/verify/stt_check.py --root . --audio audio18 --narration narration.json --ext wav --out <결과폴더>
cp <결과폴더>/audio_sync.json audio18/sync.json        # 오디오를 다시 렌더했다면 반드시 갱신
node tools/verify/sim_page.mjs http://localhost:8000
node tools/verify/scan_slides.mjs http://localhost:8000/AIStory-slide.html
```

## 해석 시 주의
- STT는 프롬프트 없이 돌린다(철자를 알려 주면 오독도 맞게 받아써 검증이 무의미해진다).
- 불일치 대부분은 연음·숫자 표기·끝부분 환각이다. 고유명사 불일치는 **STT 한계일 수 있으니 사람이 직접 들어 판정**한다.
- Windows에서 `prefers-reduced-motion`이 켜진 환경이면 `sim_page`/`probe_roll`의 기본 실행이 그 모드로 동작한다.
