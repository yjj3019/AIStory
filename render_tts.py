#!/usr/bin/env python3
"""
OmniVoice 로 「빛이 된 아이」 내레이션을 렌더링한다.

핵심 설계
---------
1. 참조 음성으로 VoiceClonePrompt 를 한 번 만들어 모든 장면에 재사용한다.
   → 전 클립의 목소리가 동일하게 유지된다. 장면마다 따로 생성하면 톤이 흔들린다.
   → 공식 문서 tips.md 도 짧은 클립에는 참조 음성 사용을 권장한다.
2. 이미 만들어진 파일은 건너뛴다. 특정 장면 문구만 고쳤을 때 그 장면만 다시 만들면 된다.
3. manifest.json 에 실제 길이를 기록한다. 웹페이지와 영상 편집 양쪽에서 쓴다.

사용법
------
    # 1) 참조 음성 준비 (본인 목소리 10~20초, 24kHz 이상, 잡음 없는 mono WAV)
    # 2) 렌더링
    python render_tts.py \
        --narration narration.json \
        --ref-audio ref/narrator.wav \
        --ref-text "안녕하세요. 오늘은 아주 오래된 이야기를 하나 들려드리려고 합니다." \
        --out-dir ../audio

    # 참조 음성 없이 성우 특성만 지정 (voice design)
    python render_tts.py --narration narration.json \
        --instruct "female, low pitch" --out-dir ../audio
    # (omnivoice는 자유 서술이 아닌 고정 키워드만 허용한다: female/male, low/high/moderate pitch,
    #  whisper, child/teenager/young adult/middle-aged/elderly, 각종 accent 등)

    # 자막용으로 한 줄씩 따로 렌더링
    python render_tts.py ... --granularity line
"""

import argparse
import json
import logging
import pathlib
import subprocess
import sys
import time

# Windows 콘솔 기본 코드페이지(cp949)는 en-dash(–) 등 일부 한글 문구 속 유니코드 문자를
# 인코딩하지 못해 UnicodeEncodeError로 즉시 죽는다. UTF-8로 강제 재설정한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

LOG = logging.getLogger("render")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="OmniVoice 내레이션 렌더러",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--narration", default="narration.json")
    ap.add_argument("--out-dir", default="../audio")
    ap.add_argument("--model", default="k2-fsa/OmniVoice")

    # 목소리 지정 (voice clone 우선, 없으면 voice design, 둘 다 없으면 auto)
    ap.add_argument("--ref-audio", default=None, help="참조 음성 WAV 경로")
    ap.add_argument("--ref-text", default=None, help="참조 음성의 정확한 전사")
    ap.add_argument(
        "--prompt-cache",
        default="voice_prompt.pt",
        help="VoiceClonePrompt 캐시. 두 번째 실행부터 참조 음성 인코딩을 건너뛴다.",
    )
    ap.add_argument(
        "--instruct",
        default=None,
        help="참조 음성이 없을 때 목소리 특성. 예: 'female, warm, low pitch'",
    )

    # 생성 파라미터 (기본값은 OmniVoice CLI 와 동일)
    ap.add_argument("--language", default="ko")
    ap.add_argument("--speed", type=float, default=0.94, help="1.0 미만이면 느리게. 동화 낭독은 0.9~0.95 권장")
    ap.add_argument("--num-step", type=int, default=32)
    ap.add_argument("--guidance-scale", type=float, default=2.0)
    ap.add_argument("--seed", type=int, default=1956, help="재현성을 위한 난수 시드")

    ap.add_argument(
        "--granularity",
        choices=["scene", "line"],
        default="scene",
        help="scene=장면당 1파일(웹페이지용), line=문장당 1파일(영상 자막 싱크용)",
    )
    ap.add_argument("--mp3", action="store_true", help="WAV 외에 MP3 도 생성 (ffmpeg 필요)")
    ap.add_argument("--force", action="store_true", help="기존 파일이 있어도 다시 생성")
    ap.add_argument("--device", default=None, help="cuda / cpu. 미지정 시 자동 선택")
    ap.add_argument(
        "--cpu-cores",
        type=int,
        default=None,
        help="CPU 렌더링 시 사용할 코어 수. 미지정(기본값)이면 가용 코어 전부 사용. "
             "공유 서버에서 자원을 아끼려면 지정한다(예: --cpu-cores 4)",
    )
    ap.add_argument("--dry-run", action="store_true", help="모델 없이 계획만 출력")
    return ap.parse_args()


def load_items(path: str, granularity: str) -> list[dict]:
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    units = []
    for item in data["items"]:
        if granularity == "scene":
            units.append({"id": item["id"], "label": item["label"], "text": item["text"]})
        else:
            for n, line in enumerate(item["lines"], start=1):
                units.append(
                    {
                        "id": f"{item['id']}-{n:02d}",
                        "label": f"{item['label']} ({n})",
                        "text": line,
                    }
                )
    return units


def to_mp3(wav: pathlib.Path) -> pathlib.Path | None:
    """웹 재생용 MP3 로 변환. 실패해도 WAV 는 그대로 쓸 수 있으므로 치명적이지 않다."""
    mp3 = wav.with_suffix(".mp3")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
           "-codec:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(mp3)]
    try:
        subprocess.run(cmd, check=True)
        return mp3
    except FileNotFoundError:
        LOG.warning("ffmpeg 가 없어 MP3 변환을 건너뜁니다. dnf install ffmpeg-free")
    except subprocess.CalledProcessError as e:
        LOG.warning("MP3 변환 실패(%s): %s", wav.name, e)
    return None


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO, force=True
    )
    args = parse_args()

    units = load_items(args.narration, args.granularity)
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    todo = [u for u in units if args.force or not (out_dir / f"{u['id']}.wav").exists()]
    LOG.info("전체 %d개 중 %d개 생성 대상", len(units), len(todo))

    if args.dry_run:
        for u in units:
            mark = "생성" if u in todo else "건너뜀"
            print(f"  [{mark}] {u['id']:<18} {len(u['text']):>4}자  {u['label']}")
        return

    if not todo:
        LOG.info("생성할 항목이 없습니다. 다시 만들려면 --force 를 쓰세요.")
    else:
        # --cpu-cores 는 BLAS/OpenMP 스레드 풀이 만들어지기 전, torch import 전에 설정해야 먹는다.
        if args.cpu_cores:
            import os as _os

            for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
                _os.environ[_var] = str(args.cpu_cores)
            if hasattr(_os, "sched_setaffinity"):
                # Linux 전용. 실제로 어느 코어를 쓸지까지 OS 레벨에서 강제한다(Windows에는 없음).
                _os.sched_setaffinity(0, set(range(args.cpu_cores)))
            LOG.info("CPU 코어 %d개로 제한합니다.", args.cpu_cores)

        # 무거운 import 는 실제로 생성할 때만 한다.
        import torch
        import soundfile as sf
        from omnivoice.models.omnivoice import OmniVoice
        from omnivoice.utils.common import get_best_device

        if args.cpu_cores:
            torch.set_num_threads(args.cpu_cores)

        device = args.device or get_best_device()
        LOG.info("모델 로딩: %s (%s)", args.model, device)
        dtype = torch.float16 if str(device).startswith("cuda") else torch.float32
        model = OmniVoice.from_pretrained(args.model, device_map=device, dtype=dtype)

        torch.manual_seed(args.seed)

        # ---- 목소리 결정 ----
        prompt = None
        if args.ref_audio:
            cache = pathlib.Path(args.prompt_cache)
            if cache.exists() and not args.force:
                from omnivoice.models.omnivoice import VoiceClonePrompt

                LOG.info("참조 음성 캐시 사용: %s", cache)
                prompt = VoiceClonePrompt.load(str(cache))
            else:
                if not args.ref_text:
                    sys.exit("--ref-audio 를 쓸 때는 --ref-text 도 필요합니다.")
                LOG.info("참조 음성 인코딩: %s", args.ref_audio)
                prompt = model.create_voice_clone_prompt(
                    ref_audio=args.ref_audio, ref_text=args.ref_text
                )
                prompt.save(str(cache))
                LOG.info("참조 음성 캐시 저장: %s", cache)
        elif args.instruct:
            LOG.info("voice design 모드: %s", args.instruct)
        else:
            LOG.warning(
                "참조 음성도 --instruct 도 없습니다. auto 모드는 장면마다 "
                "목소리가 달라질 수 있습니다. 참조 음성 사용을 권장합니다."
            )

        # ---- 생성 ----
        # tqdm 은 stdout, 로그(LOG)는 stderr 로 나눠서 진행률 표시줄이 로그 줄에 밀려 깨지지 않게 한다.
        # dry-run 경로에서는 불필요하므로 실제 생성 직전에만 import 한다.
        from tqdm import tqdm

        pbar = tqdm(todo, desc="렌더링", unit="clip", file=sys.stdout)
        for n, u in enumerate(pbar, start=1):
            pbar.set_postfix_str(u["id"])
            t0 = time.time()
            audios = model.generate(
                text=u["text"],
                language=args.language,
                voice_clone_prompt=prompt,
                instruct=args.instruct if prompt is None else None,
                speed=args.speed,
                num_step=args.num_step,
                guidance_scale=args.guidance_scale,
            )
            wav = out_dir / f"{u['id']}.wav"
            sf.write(str(wav), audios[0], model.sampling_rate)
            dur = len(audios[0]) / model.sampling_rate
            elapsed = time.time() - t0
            rtf = elapsed / max(dur, 1e-6)
            pbar.set_postfix_str(f"{u['id']} RTF={rtf:.2f}")
            LOG.info(
                "[%d/%d] %s  %.1f초 (소요 %.1f초, RTF %.3f)",
                n, len(todo), wav.name, dur, elapsed, rtf,
            )

    # ---- MP3 + manifest ----
    entries = []
    for u in units:
        wav = out_dir / f"{u['id']}.wav"
        if not wav.exists():
            LOG.warning("파일 없음: %s", wav.name)
            continue
        if args.mp3:
            to_mp3(wav)
        try:
            import wave

            with wave.open(str(wav)) as w:
                dur = w.getnframes() / w.getframerate()
        except Exception:
            dur = None
        entries.append(
            {"id": u["id"], "label": u["label"], "text": u["text"], "seconds": dur}
        )

    manifest = out_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "engine": "OmniVoice (k2-fsa)",
                "language": args.language,
                "granularity": args.granularity,
                "speed": args.speed,
                "format": "mp3" if args.mp3 else "wav",
                "items": entries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    total = sum(e["seconds"] or 0 for e in entries)
    LOG.info("완료: %d개 클립, 총 %.1f분 → %s", len(entries), total / 60, manifest)


if __name__ == "__main__":
    main()
