# ADR-0016: reconcile config-owned voice model directories

## Status

Implemented.

## Context

ADR-0007 established `awf-speech models sync` as the voice acquisition path,
but its idempotence rule retained artifacts that no current voice manifest
used. A manifest update could therefore leave obsolete TTS, VAD, wake, or
faster-whisper caches in the gitignored `models/` tree.

## Decision

After all requested acquisitions succeed, `sync_models` reconciles every
config-owned `models/{stt,tts,vad,wake}/` directory. TTS, VAD, and wake keep
only their currently manifest-listed files and `.gitkeep`. STT keeps only the
selected faster-whisper cache, its matching lock directory, `.gitkeep`, and
`CACHEDIR.TAG`; stale model caches and locks are removed. Each deletion is a
normal `REMOVED` result in the existing `models sync` JSON output.

Acquisition occurs before reconciliation. If acquisition fails, no cleanup
runs, preserving the prior working model tree.

## Consequences

Manifest edits converge model storage to the selected configuration, including
removal of `models--Systran--faster-whisper-small` when the selected STT model
changes to `deepdml/faster-whisper-large-v3-turbo-ct2`. This amends ADR-0007's
former leave-existing-artifacts behavior without changing model selection,
runtime adapters, or CLI arguments.
