# OmniVoice 내레이션 렌더러
# 빌드: podman build -t omnivoice-tts -f Containerfile .
#
# CUDA 12.4 런타임 기준. CPU 전용으로 쓰려면 base 이미지를 
# docker.io/library/python:3.12-slim 으로 바꾸고 아래 torch 설치 줄에서
# --index-url 을 제거한다.

FROM docker.io/nvidia/cuda:12.4.1-cudnn-runtime-ubi9

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/root/.cache/huggingface

RUN dnf install -y python3.12 python3.12-pip ffmpeg-free \
    && dnf clean all

RUN python3.12 -m pip install --upgrade pip \
    && python3.12 -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124 \
    && python3.12 -m pip install omnivoice

WORKDIR /work
COPY render_tts.py extract_narration.py /work/

# 모델 캐시와 출력 디렉터리는 실행 시 볼륨으로 마운트한다 (:Z 로 SELinux 레이블 지정)
VOLUME ["/root/.cache/huggingface", "/work/out"]

ENTRYPOINT ["python3.12", "/work/render_tts.py"]
CMD ["--help"]
