# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

콘텐츠 프로젝트: **「인공지능을 만든 사람들」**. AI 역사(1956 다트머스~2026 현재)를 인물의 업적·회사 이력 중심 저널리즘 톤으로 서술하는 단일 인터랙티브 페이지와, 그 내레이션을 사전 렌더링하는 TTS 파이프라인이 있다. 통합 빌드/테스트 시스템 없음 — 스크립트를 직접 실행한다.

- `AIStory.html` — 유일한 콘텐츠 산출물. 과거에는 동화형 서사(`빛이된아이.html`)와 신문 톤 팩트차트(`AI족보.html`) 두 파일로 나뉘어 있었으나 2026-09-11 하나로 병합됐다(사용자 요청 — 두 파일을 따로 유지할 이유가 없다고 판단). 스크롤 기반 15장 서사(`SCENES` 배열) + 클릭 가능한 SVG 인물 계보도(`P`/`ORG`/`E` 데이터, 옛 `AI족보.html`에서 이식) + 전 장에 적용된 클릭형 인물 카드(`data-map` + `wireMap()`, 옛 `빛이된아이.html` 13장 전용이던 패턴을 일반화)로 구성된다.
- `extract_narration.py`, `render_tts.py`, `narration.json`, `Containerfile`은 모두 이 디렉터리 **루트**에 있다(`tts/` 하위 아님). Windows 콘솔(cp949)에서도 정상 출력되도록 두 파이썬 스크립트 모두 시작 부분에서 stdout/stderr를 UTF-8로 재설정한다 — 이 재설정을 제거하면 en-dash 등 특수 문자가 섞인 장면 라벨 출력 시 다시 크래시한다.

## Architecture — single source of truth 흐름

```
AIStory.html (SCENES 배열)     ← 문구의 유일한 원본
        │  extract_narration.py
        ▼
   narration.json               ← 오프닝 1 + 15장 + 엔딩 1 = 17개 항목
        │  render_tts.py (OmniVoice, k2-fsa)
        ▼
   audio/NN-scene.{mp3,wav}     ← 웹페이지가 자동 탐지해서 재생
   audio/manifest.json          ← 클립별 실측 길이 (영상 편집용)
```

- **HTML이 유일한 원본**이다. 대사를 고치려면 `AIStory.html`의 `SCENES` 배열만 고치고, `extract_narration.py`를 재실행해 `narration.json`을 동기화한다. `narration.json`을 직접 편집하지 않는다.
- `extract_narration.py`는 정규식으로 `const SCENES = [ ... \n];` 블록과 `year:'...'`, `lines:[...]`를 파싱한다. HTML의 이 구조(변수명, 들여쓰기 패턴)를 바꾸면 파서도 함께 고쳐야 한다. 오프닝/엔딩 문구는 HTML이 아니라 `extract_narration.py` 안의 `OPENING`/`ENDING` 상수에 하드코딩되어 있다.
- 파일명 규칙은 `NN-scene`(2자리, 1-base) / `00-opening` / `16-ending`으로 고정이며, HTML 쪽 `clipName()`과 `render_tts.py`의 `id` 생성 로직이 이 규칙에 동시에 의존한다. 규칙을 바꾸려면 양쪽을 함께 수정한다. 오프닝/엔딩은 `speakText('00-opening', OPENING_TEXT, ...)` / `speakText('16-ending', ENDING_TEXT, ...)`로 재생 흐름(`start()`/`afterScene()`)에 명시적으로 연결돼 있다 — `SCENES` 배열만 순회하는 루프에 다시 흡수시키지 말 것(오프닝/엔딩이 재생되지 않던 과거 버그의 재발 방지).
- `OPENING_TEXT`는 HTML에 하드코딩돼 있고 `extract_narration.py`의 `OPENING` 상수와 별개다 — 오프닝 문구를 바꾸면 두 곳을 모두 고쳐야 한다. `ENDING_TEXT`는 `#closing .quote` DOM에서 읽어와 중복이 없다.
- 웹페이지는 `audio/<id>.mp3` 또는 `.wav`를 찾아, **있으면 그걸 쓰고 없으면 브라우저 내장 TTS로 자동 폴백**한다(`AUDIO_DIR`/`getClip`/엔진 표시 로직). 오디오가 아직 없어도 페이지는 항상 정상 동작해야 한다는 게 설계 전제 — 이를 깨는 변경(오디오 필수화 등)은 하지 않는다.
- `render_tts.py`는 참조 음성(`--ref-audio`)으로 `VoiceClonePrompt`를 **한 번만** 만들어 `voice_prompt.pt`에 캐시하고 17개 클립 전체에 재사용한다. 장면마다 새로 생성하면 목소리 톤이 흔들리므로, 이 캐시-재사용 구조를 우회하는 변경은 피한다.
- 이미 존재하는 `audio/<id>.wav`는 `--force` 없이는 건너뛴다 — 특정 장면 문구만 고쳤을 때 해당 파일만 지우고 재실행하는 증분 워크플로우를 전제로 한다.

## Commands

```bash
# 1) HTML → narration.json (SCENES 문구를 고친 뒤에는 항상 재실행)
python extract_narration.py AIStory.html -o narration.json

# 2) 생성 계획만 확인 (모델 불필요)
python render_tts.py --narration narration.json --out-dir ./audio --dry-run

# 3) 실제 렌더링 (OmniVoice, GPU 권장)
python render_tts.py \
    --narration narration.json \
    --ref-audio ref/narrator.wav \
    --ref-text "<참조 음성을 발음한 그대로 정확히 옮긴 텍스트>" \
    --out-dir ./audio \
    --speed 0.94 \
    --mp3

# 특정 장면만 재생성
rm audio/06-scene.*
python render_tts.py --narration narration.json --ref-audio ref/narrator.wav \
    --ref-text "..." --out-dir ./audio --mp3   # 기존 06-scene.wav가 없으므로 자동 재생성됨

# 결과 확인 (file:// 로도 동작하나 HTTP 권장)
python -m http.server 8000   # http://localhost:8000/AIStory.html

# 컨테이너로 렌더링 (RHEL/Podman, GPU)
podman build -t omnivoice-tts -f Containerfile .
podman run --rm --device nvidia.com/gpu=all \
    -v ./narration.json:/work/narration.json:ro,Z \
    -v ./ref:/work/ref:ro,Z \
    -v ./audio:/work/out:Z \
    -v ~/.cache/huggingface:/root/.cache/huggingface:Z \
    omnivoice-tts \
    --narration /work/narration.json --ref-audio /work/ref/narrator.wav \
    --ref-text "..." --out-dir /work/out --mp3
```

- 자동 테스트/린트 없음. 검증은 `--dry-run`(로직) → 실제 렌더링(음질/발음) → 브라우저 확인(재생/폴백) 순으로 수동 진행한다.
- 무거운 의존성(`torch`, `omnivoice`, `soundfile`)은 `render_tts.py`에서 실제 생성이 필요한 시점에만 지연 import된다 — `--dry-run`은 이 패키지들 없이도 동작해야 하므로, 이 지연 import 구조를 깨지 않는다.
- `render_tts.py --granularity line`은 장면당이 아닌 문장당 1개 파일을 만든다(영상 자막 싱크용) — 웹페이지 재생에는 쓰이지 않는 별도 산출 모드.

## Environment notes

- 설치 대상은 RHEL/Rocky, Python 3.10+, `torch>=2.4` (CUDA 12.4 인덱스). SELinux Enforcing 환경이므로 컨테이너 볼륨 마운트에는 `:Z` 레이블이 필요하다(`setenforce 0` 금지 — 워크스페이스 전역 규칙).
- 모델 첫 실행 시 Hugging Face에서 수 GB를 내려받는다; 폐쇄망/제한된 환경에서는 이 단계가 blocker가 될 수 있다.
- GPU 유무를 가정하지 말 것 — 개발 PC에 NVIDIA GPU가 없으면 `torch.cuda.is_available()`이 `False`이므로 `--device cpu`를 명시하고, CPU 추론은 README 기준으로 훨씬 느리다는 점을 미리 안내한다.
