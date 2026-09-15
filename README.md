# OmniVoice 내레이션 파이프라인

브라우저 내장 TTS를 [k2-fsa/OmniVoice](https://github.com/k2-fsa/OmniVoice) 로 교체한다.

## 왜 사전 렌더링 방식인가

OmniVoice는 PyTorch 기반이라 브라우저에서 직접 돌지 않는다. 실시간 합성이 필요하면 서버를
띄워야 하는데, 이 이야기의 내레이션은 **한 번 만들어 두면 바뀌지 않는 고정 텍스트 17개**다.
미리 렌더링해서 파일로 두는 편이 품질·속도·재현성 모두 유리하고, 최종 목표인 영상 제작에도
그대로 쓸 수 있다.

```
AIStory.html                ← 문구의 원본
        │
        │ extract_narration.py
        ▼
   narration.json       ← 17개 항목 (오프닝 + 15장 + 엔딩)
        │
        │ render_tts.py  (OmniVoice)
        ▼
   audio/*.wav|mp3      ← 웹페이지가 자동으로 찾아 재생
   audio/manifest.json  ← 클립별 실제 길이 (영상 편집용)
```

웹페이지는 `audio/01-scene.mp3` 또는 `.wav` 를 찾는다. **있으면 그걸 쓰고, 없으면 브라우저
내장 음성으로 자동 전환**한다. 재생 바 오른쪽에 현재 어떤 엔진인지 표시된다.

## 확인된 사실

저장소를 직접 받아 확인한 내용이다.

| 항목 | 내용 |
|---|---|
| 한국어 지원 | `ko` / 학습 데이터 8,609시간 (지원 600여 개 언어 중 상위권) |
| 라이선스 | Apache-2.0 (모델·코드) |
| 요구 Python | 3.10 이상 |
| 주요 의존성 | torch>=2.4, torchaudio, transformers>=5.3, soundfile, librosa, pydub |
| 속도 | H100 fp16 기준 RTF 0.025 (실시간의 40배). CPU도 동작하나 훨씬 느림 |
| 짧은 클립 | 공식 문서상 참조 음성 없이는 1~2초 클립이 불안정. **voice cloning 권장** |

## 설치 (RHEL / Rocky)

```bash
sudo dnf install -y python3.12 python3.12-devel gcc-c++ ffmpeg-free

python3.12 -m venv ~/venv/omnivoice
source ~/venv/omnivoice/bin/activate
pip install --upgrade pip

# GPU (CUDA 12.x). CPU만 쓸 경우 이 줄은 건너뛴다.
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

pip install omnivoice
```

설치 확인:

```bash
python -c "import torch,omnivoice; print(torch.__version__, torch.cuda.is_available())"
```

## 참조 음성 준비

목소리 일관성이 이 파이프라인의 핵심이다. `create_voice_clone_prompt()` 로 참조 음성을
한 번만 인코딩해 17개 클립 전부에 재사용하므로, 장면 사이에 톤이 흔들리지 않는다.

권장 조건:

- 길이 10~20초, mono, 24kHz 이상 WAV
- 배경 소음·리버브 없이 조용한 곳에서 녹음
- **실제로 낭독할 톤 그대로** 읽는다. 빠르게 읽은 참조 음성을 주면 결과도 빨라진다
- 전사(`--ref-text`)는 발음한 그대로 정확히 적는다

동화 낭독용 예시 문장:

> 안녕하세요. 오늘은 아주 오래된 이야기를 하나 들려드리려고 합니다. 천천히, 편안하게 들어 주세요.

## 실행

아래 명령은 모두 이 디렉터리(`AIStory/`) 루트에서 실행한다 — `extract_narration.py`, `render_tts.py`,
`narration.json`, `Containerfile`이 `tts/` 하위가 아니라 이 디렉터리에 바로 있다.

```bash
python extract_narration.py AIStory.html -o narration.json

python render_tts.py \
    --narration narration.json \
    --ref-audio ref/narrator.wav \
    --ref-text "안녕하세요. 오늘은 아주 오래된 이야기를 하나 들려드리려고 합니다. 천천히, 편안하게 들어 주세요." \
    --out-dir ./audio \
    --speed 0.94 \
    --mp3
```

이 저장소 환경에는 GPU가 없다면 `--device cpu`를 추가한다(자동 감지되지만 명시하는 편이 안전하다).
Windows 콘솔(cp949)에서 실행할 경우 스크립트가 UTF-8 출력으로 자동 전환하도록 이미 처리돼 있다.

첫 실행 시 모델을 Hugging Face에서 내려받는다(수 GB). 이후에는 캐시를 쓴다.

주요 옵션:

| 옵션 | 설명 |
|---|---|
| `--speed 0.94` | 낭독 속도. 동화는 0.90~0.95가 자연스럽다 |
| `--granularity line` | 문장당 파일 1개. 영상 자막 싱크를 정밀하게 맞출 때 |
| `--force` | 기존 파일을 무시하고 다시 생성 |
| `--dry-run` | 모델 없이 생성 계획만 확인 |
| `--instruct "female, low pitch"` | 참조 음성 없이 목소리 특성만 지정 |
| `--seed 1956` | 재현성 확보 |

특정 장면 문구만 고쳤다면 그 파일만 지우고 다시 돌리면 된다.

```bash
rm ./audio/06-scene.*
python render_tts.py --narration narration.json --ref-audio ref/narrator.wav \
    --ref-text "..." --out-dir ./audio --mp3
```

## 결과 확인

```bash
python -m http.server 8000
# 브라우저에서 http://localhost:8000/AIStory.html
```

재생 바 오른쪽이 **"고품질 음성"** 이면 렌더링된 파일을 쓰는 중이다. "브라우저 음성"이면
`audio/` 안의 파일 이름이 `01-scene.mp3` 형식인지 확인한다.

`file://` 로 직접 열어도 동작하지만, HTTP로 서빙하는 편이 안정적이다.

## 컨테이너로 돌리기 (선택)

```bash
podman build -t omnivoice-tts -f Containerfile .

podman run --rm \
    --device nvidia.com/gpu=all \
    -v ./narration.json:/work/narration.json:ro,Z \
    -v ./ref:/work/ref:ro,Z \
    -v ../audio:/work/out:Z \
    -v ~/.cache/huggingface:/root/.cache/huggingface:Z \
    omnivoice-tts \
    --narration /work/narration.json --ref-audio /work/ref/narrator.wav \
    --ref-text "..." --out-dir /work/out --mp3
```

볼륨에 `:Z` 를 붙여 SELinux 레이블을 맞춘다. `setenforce 0` 은 필요 없다.
HF 캐시를 마운트해야 매번 모델을 다시 받지 않는다.

## 영상 제작으로 넘어갈 때

`audio/manifest.json` 에 클립별 실제 길이가 초 단위로 들어 있다. 장면 전환 타이밍을
여기에 맞추면 된다.

```bash
python - <<'EOF'
import json
m=json.load(open('audio/manifest.json'))
t=0
for it in m['items']:
    print(f"{t//60:02.0f}:{t%60:05.2f}  {it['label']}")
    t += (it['seconds'] or 0) + 1.5   # 장면 사이 1.5초 여백
EOF
```

전체를 한 파일로 합치려면:

```bash
cd audio
ls *.mp3 | sort | sed "s/^/file '/;s/$/'/" > list.txt
ffmpeg -f concat -safe 0 -i list.txt -c copy narration_full.mp3
```

## 문제 해결

**CUDA out of memory** — `--device cpu` 로 확인 후, GPU 메모리가 부족하면 다른 프로세스를
정리한다. 이 작업은 배치 없이 한 문장씩 처리하므로 요구량이 크지 않다.

**목소리가 장면마다 다르다** — 참조 음성 없이 auto 모드로 돌린 경우다. `--ref-audio` 를
지정하거나, 최소한 `--instruct` 를 고정해서 다시 생성한다.

**숫자를 이상하게 읽는다** — `"2026년"` 같은 표기는 대개 잘 처리하지만, 문제가 있으면
HTML 원문을 `"이천이십육 년"` 처럼 고치고 `extract_narration.py` 를 다시 돌린다.
`omnivoice[tn]` 의 텍스트 정규화는 중국어·영어 위주라 한국어에는 큰 도움이 되지 않는다.

**발음이 어색한 고유명사** — 「챗지피티」, 「오픈에이아이」처럼 이미 한글 음차로 적어 두었다.
새 고유명사를 넣을 때도 로마자 대신 한글로 적는 편이 안정적이다.
