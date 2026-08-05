"""`awf-speech` console entry point (Section 16.4, ADR-0008).

`round-trip` is a standalone entry point for `run_voice_round_trip`, so a
non-Python caller (the Electron GUI's main process) can invoke it the same
way it already spawns `awf serve --stdio`: as a subprocess, reading one JSON
object from stdout. This is push-to-talk-by-file: the caller supplies a
wake-word audio file and a command audio file rather than a live microphone
stream.

`models sync`/`models verify` resolve STT readiness (the only readiness
result `speech.models` needs), then acquire or check presence of the
artifacts `config/voice/{stt,tts,vad,wake}.yaml` name.
"""

import argparse
import json
import sys
from pathlib import Path

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.paths import REPO_ROOT, db_path
from awf.speech.models import artifact_paths, sync_models, verify_models
from awf.speech.pipeline import VoicePipelineError, run_voice_round_trip


def _echo_core(command_text: str) -> str:
    return f"Acknowledged: {command_text.strip()}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="awf-speech")
    sub = parser.add_subparsers(dest="command", required=True)

    round_trip = sub.add_parser("round-trip")
    round_trip.add_argument("wake_audio_path")
    round_trip.add_argument("command_audio_path")
    round_trip.add_argument("--voice-id", default="bf_isabella")
    round_trip.add_argument("--response-audio-out", required=True)

    models = sub.add_parser("models")
    models_sub = models.add_subparsers(dest="models_command", required=True)
    models_sub.add_parser("sync")
    models_sub.add_parser("verify")

    return parser


def _run_round_trip(args: argparse.Namespace, repo_root: Path) -> int:
    wake_paths = artifact_paths(repo_root, "wake")
    vad_paths = artifact_paths(repo_root, "vad")
    tts_paths = artifact_paths(repo_root, "tts")

    conn_db_path = db_path(repo_root)
    init_db(conn_db_path)
    conn = get_connection(conn_db_path)

    try:
        result = run_voice_round_trip(
            conn,
            repo_root=repo_root,
            wake_audio_path=Path(args.wake_audio_path),
            command_audio_path=Path(args.command_audio_path),
            wake_model_path=wake_paths["hey_jarvis_v0.1.onnx"],
            wake_melspec_model_path=wake_paths["melspectrogram.onnx"],
            wake_embedding_model_path=wake_paths["embedding_model.onnx"],
            vad_model_path=vad_paths["silero_vad.onnx"],
            tts_model_path=tts_paths["kokoro-v1.0.onnx"],
            tts_voices_path=tts_paths["voices-v1.0.bin"],
            voice_id=args.voice_id,
            core_fn=_echo_core,
        )
    except VoicePipelineError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    finally:
        conn.close()

    from awf.speech.tts_kokoro import write_wav

    samples, sample_rate = result.response_audio
    write_wav(samples, sample_rate, Path(args.response_audio_out))

    print(
        json.dumps(
            {
                "hardware_profile_id": result.hardware_profile_id,
                "wake_detected": result.wake_detected,
                "wake_score": result.wake_score,
                "speech_segments": result.speech_segments,
                "command_text": result.command_text,
                "command_language": result.command_language,
                "response_text": result.response_text,
                "response_audio_path": args.response_audio_out,
            }
        )
    )
    return 0


def _run_models(args: argparse.Namespace, repo_root: Path) -> int:
    from awf.hardware.preflight import collect_preflight_tokens
    from awf.hardware.profiler import collect_inventory
    from awf.hardware.readiness import derive_stt_readiness

    inventory = collect_inventory()
    tokens = collect_preflight_tokens(inventory)
    stt_device = derive_stt_readiness(inventory, tokens).device

    if args.models_command == "sync":
        results = sync_models(repo_root, stt_device)
        ok = True
    else:
        results = verify_models(repo_root)
        ok = all(result["status"] == "OK" for result in results)

    print(json.dumps({"stt_device": stt_device, "results": results}))
    return 0 if ok else 1


def run(argv: list[str], repo_root: Path) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "round-trip":
        return _run_round_trip(args, repo_root)
    if args.command == "models":
        return _run_models(args, repo_root)
    raise AssertionError(f"unhandled command: {args.command}")


def main() -> int:
    return run(sys.argv[1:], REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
