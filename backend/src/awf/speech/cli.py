"""Standalone entry point for `run_voice_round_trip`, so a non-Python caller
(the Electron GUI's main process, Section 16.4) can invoke it the same way
it already spawns `awf serve --stdio`: as a subprocess, reading one JSON
object from stdout.

This is push-to-talk-by-file: the caller supplies a wake-word audio file and
a command audio file rather than a live microphone stream.
"""

import argparse
import json
import sys
from pathlib import Path

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.speech.pipeline import VoicePipelineError, run_voice_round_trip


def _repo_root() -> Path:
    # backend/src/awf/speech/cli.py -> speech -> awf -> src -> backend -> <repo root>
    return Path(__file__).resolve().parents[4]


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

    return parser


def run(argv: list[str], repo_root: Path) -> int:
    args = build_parser().parse_args(argv)
    models = repo_root / "models"

    db_path = repo_root / "data" / "awf_db" / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)

    try:
        result = run_voice_round_trip(
            conn,
            wake_audio_path=Path(args.wake_audio_path),
            command_audio_path=Path(args.command_audio_path),
            wake_model_path=models / "wake" / "hey_jarvis_v0.1.onnx",
            vad_model_path=models / "vad" / "silero_vad.onnx",
            tts_model_path=models / "tts" / "kokoro-v1.0.onnx",
            tts_voices_path=models / "tts" / "voices-v1.0.bin",
            voice_id=args.voice_id,
            core_fn=_echo_core,
            stt_download_root=models / "stt",
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


def main() -> int:
    return run(sys.argv[1:], _repo_root())


if __name__ == "__main__":
    sys.exit(main())
