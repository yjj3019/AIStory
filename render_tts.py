#!/usr/bin/env python3
"""
OmniVoice 로 「인공지능을 만든 사람들」 내레이션을 렌더링한다.

핵심 설계
---------
1. 참조 음성으로 VoiceClonePrompt 를 한 번 만들어 모든 장면에 재사용한다.
   → 모든 클립의 목소리가 동일하게 유지된다. 장면마다 따로 생성하면 톤이 흔들린다.
   → 공식 문서 tips.md 도 짧은 클립에는 참조 음성 사용을 권장한다.
2. 이미 만들어진 파일은 건너뛴다(manifest 의 문구와 일치할 때만). 문구가 바뀐 장면은 자동으로 다시 만든다.
3. manifest.json 에 실제 길이를 기록한다. 웹페이지와 영상 편집 양쪽에서 쓴다.

사용법
------
    # 1) 참조 음성 준비 (본인 목소리 10~20초, 24kHz 이상, 잡음 없는 mono WAV)
    # 2) 렌더링
    python render_tts.py \
        --narration narration.json \
        --ref-audio ref/narrator.wav \
        --ref-text "안녕하세요. 오늘은 아주 오래된 이야기를 하나 들려드리려고 합니다." \
        --out-dir audio18

    # 참조 음성 없이 성우 특성만 지정 (voice design)
    python render_tts.py --narration narration.json \
        --instruct "female, low pitch" --out-dir audio18
    # (omnivoice는 자유 서술이 아닌 고정 키워드만 허용한다: female/male, low/high/moderate pitch,
    #  whisper, child/teenager/young adult/middle-aged/elderly, 각종 accent 등)

    # 자막용으로 한 줄씩 따로 렌더링
    python render_tts.py ... --granularity line
"""

import argparse
import hashlib
import json
import logging
import math
import pathlib
import subprocess
import sys
import tempfile
import time
import wave

LOG = logging.getLogger("render")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="OmniVoice 내레이션 렌더러",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--narration", default="narration.json")
    ap.add_argument("--out-dir", default="audio18")
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
    ap.add_argument("--force", action="store_true", help="기존 클립이 있어도 다시 생성(참조 음성 캐시는 건드리지 않는다)")
    ap.add_argument("--refresh-prompt", action="store_true",
                    help="참조 음성 캐시(voice_prompt.pt)를 다시 인코딩해 덮어쓴다. 목소리가 바뀌므로 신중히")
    ap.add_argument("--reuse", action="append", default=[], metavar="ID",
                    help="문구 검증 기록(.sha1/manifest)이 없어도 이 id 의 기존 wav 를 그대로 쓴다(예: 다른 곳에서 복사한 00-opening). 여러 번 지정 가능")
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


def _file_sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _script_matches(entry: dict, text: str) -> bool:
    """Legacy SHA1 can veto conflicting evidence, but cannot prove provenance."""
    evidence = []
    if "text" in entry:
        evidence.append(entry["text"] == text)
    if "text_sha256" in entry:
        evidence.append(entry["text_sha256"] == _text_sha256(text))
    if not evidence or not all(evidence):
        return False
    return "text_sha1" not in entry or entry["text_sha1"] == hashlib.sha1(text.encode("utf-8")).hexdigest()


def wav_provenance_matches(unit: dict, wav: pathlib.Path, previous: dict | None = None) -> bool:
    """Require a script hash bound to these exact WAV bytes, never --reuse alone."""
    if not wav.is_file() or not wav.stat().st_size:
        return False
    wav_hash = _file_sha256(wav)
    proof = wav.with_suffix(".provenance.json")
    if proof.exists():
        try:
            entry = json.loads(proof.read_text(encoding="utf-8"))
            return isinstance(entry, dict) and _script_matches(entry, unit["text"]) and entry.get("wav_sha256") == wav_hash
        except (OSError, ValueError, TypeError):
            return False
    entry = previous or {}
    if not _script_matches(entry, unit["text"]):
        return False
    # MP3 manifests can carry their source WAV digest. A WAV manifest binds
    # audio_sha256 directly only when its file names this exact WAV.
    expected = entry.get("wav_sha256")
    if expected is None and entry.get("file") == wav.name:
        expected = entry.get("audio_sha256")
    return expected == wav_hash


def record_wav_provenance(unit: dict, wav: pathlib.Path) -> None:
    """Call only immediately after successful generation of this unit's WAV."""
    proof = wav.with_suffix(".provenance.json")
    pending = proof.with_suffix(".json.part")
    pending.write_text(json.dumps({"id": unit["id"], "text_sha256": _text_sha256(unit["text"]),
                                   "wav_sha256": _file_sha256(wav)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(proof)


def to_mp3(wav: pathlib.Path) -> pathlib.Path | None:
    """Atomically replace the MP3 only after conversion succeeds and is nonempty."""
    mp3 = wav.with_suffix(".mp3")
    with tempfile.NamedTemporaryFile(prefix=wav.stem + ".", suffix=".part.mp3", dir=wav.parent, delete=False) as stream:
        pending = pathlib.Path(stream.name)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
           "-codec:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", str(pending)]
    try:
        subprocess.run(cmd, check=True)
        if not pending.is_file() or pending.stat().st_size == 0:
            LOG.warning("MP3 변환 결과가 비어 있습니다: %s", wav.name)
            return None
        pending.replace(mp3)
        return mp3
    except FileNotFoundError:
        LOG.warning("ffmpeg 가 없어 MP3 변환을 건너뜁니다. dnf install ffmpeg-free")
    except (subprocess.CalledProcessError, OSError) as exc:
        LOG.warning("MP3 변환 실패(%s): %s", wav.name, exc)
    finally:
        pending.unlink(missing_ok=True)
    return None


def probe_audio_seconds(path: pathlib.Path) -> float | None:
    """Measure the final selected format; never substitute WAV time for MP3."""
    try:
        if path.suffix.lower() == ".wav":
            with wave.open(str(path)) as wav:
                duration = wav.getnframes() / wav.getframerate()
        else:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
        return duration if math.isfinite(duration) and duration > 0 else None
    except (OSError, ValueError, subprocess.CalledProcessError, EOFError, ZeroDivisionError, wave.Error) as exc:
        LOG.warning("최종 오디오 길이를 측정하지 못했습니다(%s): %s", path.name, exc)
        return None


def make_manifest_entry(unit: dict, wav: pathlib.Path, output: pathlib.Path | None, *,
                        wav_verified: bool, output_format: str, duration_probe=None) -> dict:
    """Bind only successfully produced bytes to proven source text.

    Passing output=None after conversion failure prevents a leftover MP3 from
    gaining current script hashes. Unknown --reuse input never gains text proof.
    duration_probe injection lets tests use synthetic bytes without codecs/TTS.
    """
    duration_probe = duration_probe or probe_audio_seconds
    available = output is not None and output.is_file() and output.stat().st_size > 0
    duration = duration_probe(output) if available else None
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        duration = None
    trusted = wav_verified and available
    entry = {
        "id": unit["id"], "label": unit["label"],
        "requested_text_sha256": _text_sha256(unit["text"]),
        "file": wav.with_suffix("." + output_format).name,
        "audio_sha256": _file_sha256(output) if available else None,
        "wav_sha256": _file_sha256(wav) if wav_verified else None,
        "seconds": duration,
        "output_status": "ready" if available else "missing_or_conversion_failed",
        "provenance_status": "verified" if trusted else "unverified",
        "quality_status": "pending_review" if trusted and duration is not None else "unreviewed",
    }
    if trusted:
        entry.update({"text": unit["text"],
                      "text_sha1": hashlib.sha1(unit["text"].encode("utf-8")).hexdigest(),
                      "text_sha256": _text_sha256(unit["text"])})
    return entry


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO, force=True
    )
    args = parse_args()

    units = load_items(args.narration, args.granularity)
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read prior proof; an unverified reused WAV may be skipped explicitly,
    # but it must never be relabeled as having the requested script.
    previous = {}
    prev_manifest = out_dir / "manifest.json"
    try:
        entries = json.loads(prev_manifest.read_text(encoding="utf-8")).get("items", [])
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or entry["id"] in previous:
                raise ValueError("invalid or duplicate manifest id")
            previous[entry["id"]] = entry
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        previous = {}
        LOG.warning("기존 manifest 검증 기록을 읽을 수 없습니다(%s). 검증되지 않은 WAV는 다시 생성합니다.", exc)

    wav_verified = {unit["id"]: wav_provenance_matches(
        unit, out_dir / f"{unit['id']}.wav", previous.get(unit["id"])) for unit in units}

    def stale(unit: dict) -> bool:
        return (out_dir / f"{unit['id']}.wav").is_file() and not wav_verified[unit["id"]] and unit["id"] not in args.reuse

    todo = [
        u for u in units
        if args.force or not (out_dir / f"{u['id']}.wav").exists() or stale(u)
    ]
    stale_ids = [u["id"] for u in units if stale(u)]
    if stale_ids:
        LOG.warning("문구가 바뀌었거나 검증 기록이 없어 다시 만드는 기존 클립 %d개: %s", len(stale_ids), ", ".join(stale_ids))
    LOG.info("전체 %d개 중 %d개 생성 대상", len(units), len(todo))

    if args.dry_run:
        for u in units:
            mark = ("생성(문구 변경)" if u["id"] in stale_ids else "생성") if u in todo else "건너뜀"
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

        # 잘못된 인자는 모델 로딩(CPU 에서 수 분) 전에 걸러낸다.
        _cache_ok = pathlib.Path(args.prompt_cache).exists() and not args.refresh_prompt and not args.instruct
        if args.refresh_prompt and not args.ref_audio:
            sys.exit("--refresh-prompt 는 --ref-audio 와 --ref-text 가 필요합니다.")
        if args.ref_audio and not _cache_ok and not args.ref_text:
            sys.exit("--ref-audio 를 쓸 때는 --ref-text 도 필요합니다.")

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
        cache = pathlib.Path(args.prompt_cache)
        if cache.exists() and not args.refresh_prompt and not args.instruct:
            # --ref-audio 를 안 줘도 캐시가 있으면 반드시 그것을 쓴다(일부 클립만 다시 만들 때 톤이 달라지는 사고 방지).
            from omnivoice.models.omnivoice import VoiceClonePrompt

            LOG.info("참조 음성 캐시 사용: %s", cache.resolve())
            prompt = VoiceClonePrompt.load(str(cache))
        elif args.ref_audio:
            if not args.ref_text:
                sys.exit("--ref-audio 를 쓸 때는 --ref-text 도 필요합니다.")
            LOG.info("참조 음성 인코딩: %s", args.ref_audio)
            prompt = model.create_voice_clone_prompt(
                ref_audio=args.ref_audio, ref_text=args.ref_text
            )
            if cache.exists():
                bak = cache.with_name(cache.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
                cache.replace(bak)
                LOG.warning("기존 캐시를 %s 로 보존했습니다.", bak.name)
            prompt.save(str(cache))
            LOG.info("참조 음성 캐시 저장: %s", cache.resolve())
        elif args.instruct:
            LOG.info("voice design 모드: %s", args.instruct)
        else:
            LOG.warning(
                "참조 음성도 --instruct 도 없습니다. auto 모드는 장면마다 "
                "목소리가 달라질 수 있습니다. 참조 음성 사용을 권장합니다."
            )

        # ---- 생성 ----
        # tqdm 은 stdout, 로그(LOG)는 stderr 로 나눠서 진행률 표시줄이 로그 줄에 밀려 깨지지 않게 한다.
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
            part = out_dir / f"{u['id']}.wav.part"
            sf.write(str(part), audios[0], model.sampling_rate, format="WAV")
            part.replace(wav)                                # 도중에 죽어도 잘린 wav 가 남지 않는다
            (out_dir / f"{u['id']}.sha1").write_text(hashlib.sha1(u["text"].encode("utf-8")).hexdigest() + "\n", encoding="utf-8")   # 이 wav 가 어떤 문구로 만들어졌는지 클립 단위로 기록
            record_wav_provenance(u, wav)
            wav_verified[u["id"]] = True
            (out_dir / f"{u['id']}.mp3").unlink(missing_ok=True)   # 옛 mp3 가 새 wav 를 가리지 않게
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
    failed_ids = []
    for unit in units:
        wav = out_dir / f"{unit['id']}.wav"
        if not wav.is_file():
            LOG.warning("파일 없음: %s", wav.name)
            failed_ids.append(unit["id"])
            continue
        output = to_mp3(wav) if args.mp3 else wav
        entry = make_manifest_entry(unit, wav, output,
                                    wav_verified=wav_provenance_matches(unit, wav, previous.get(unit["id"])),
                                    output_format="mp3" if args.mp3 else "wav")
        entries.append(entry)
        if entry["output_status"] != "ready" or entry["seconds"] is None:
            failed_ids.append(unit["id"])

    manifest = out_dir / "manifest.json"
    pending_manifest = manifest.with_suffix(".json.part")
    pending_manifest.write_text(
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

    pending_manifest.replace(manifest)
    total = sum(e["seconds"] or 0 for e in entries)
    LOG.info("완료: %d개 클립, 총 %.1f분 → %s", len(entries), total / 60, manifest)

    if failed_ids:
        LOG.error("변환 또는 최종 길이 검증이 완료되지 않은 클립 %d개: %s", len(failed_ids), ", ".join(failed_ids))
        sys.exit(2)


if __name__ == "__main__":
    main()
