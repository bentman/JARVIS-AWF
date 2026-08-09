"""LLM model discovery and binary acquisition (ADR-0017)."""

import os
import shutil
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from awf.llm.servers import Artifact, LlmServerError
from awf.paths import llm_models_dir, runtimes_dir


@dataclass(frozen=True)
class LocalModel:
    name: str  # directory under models/llm/<name>
    files: tuple[Path, ...]  # *.gguf files, sorted
    primary: Path  # the largest .gguf file


def local_models(repo_root: Path) -> tuple[LocalModel, ...]:
    models_base = llm_models_dir(repo_root)
    if not models_base.is_dir():
        return ()

    result: list[LocalModel] = []
    for item in sorted(models_base.iterdir()):
        if not item.is_dir():
            continue
        gguf_files = sorted([f for f in item.iterdir() if f.is_file() and f.name.endswith(".gguf")])
        if not gguf_files:
            continue
        # Primary is the largest .gguf file (tie breaker by path)
        primary = max(gguf_files, key=lambda f: (f.stat().st_size, str(f)))
        result.append(LocalModel(name=item.name, files=tuple(gguf_files), primary=primary))

    return tuple(result)


def model_by_name(repo_root: Path, name: str) -> LocalModel:
    all_m = local_models(repo_root)
    # Check directory name match
    for m in all_m:
        if m.name == name:
            return m
    # Check primary GGUF filename match
    for m in all_m:
        if m.primary.name == name:
            return m
    # Check any GGUF filename match
    for m in all_m:
        if any(f.name == name for f in m.files):
            return m

    model_dir = llm_models_dir(repo_root) / name
    if not model_dir.is_dir():
        raise LlmServerError(f"Local model '{name}' not found under '{llm_models_dir(repo_root)}'")
    raise LlmServerError(f"Local model directory '{name}' contains no .gguf artifacts")



def binary_path(repo_root: Path, profile_id: str, artifact: Artifact) -> Path:
    return runtimes_dir(repo_root) / "llama.cpp" / profile_id / artifact.binary


def acquire_binary(repo_root: Path, profile_id: str, artifact: Artifact) -> dict:
    target_binary = binary_path(repo_root, profile_id, artifact)
    if target_binary.is_file() and target_binary.stat().st_size > 0:
        return {
            "profile_id": profile_id,
            "status": "PRESENT",
            "path": str(target_binary),
            "url": artifact.url,
        }

    cache_dir = repo_root / "cache" / "llm" / profile_id
    cache_dir.mkdir(parents=True, exist_ok=True)

    archive_filename = Path(artifact.url).name
    archive_path = cache_dir / archive_filename

    scratch_dir = cache_dir / "extract_scratch"
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 2: download artifact
        with urllib.request.urlopen(artifact.url) as resp, open(archive_path, "wb") as out_f:
            shutil.copyfileobj(resp, out_f)

        # Step 3: extract archive
        if artifact.archive == "tar_gz":
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=scratch_dir)
        elif artifact.archive == "zip":
            with zipfile.ZipFile(archive_path, "r") as zip_f:
                zip_f.extractall(path=scratch_dir)
        else:
            raise LlmServerError(f"Unsupported archive format '{artifact.archive}' for artifact '{profile_id}'")

        # Step 4: locate artifact.binary inside extracted tree
        found_binary: Path | None = None
        for root, _, files in os.walk(scratch_dir):
            if artifact.binary in files:
                found_binary = Path(root) / artifact.binary
                break

        if found_binary is None:
            raise LlmServerError(
                f"Binary '{artifact.binary}' not found inside extracted archive '{archive_filename}' for '{profile_id}'"
            )

        # Step 5: copy containing directory flat into target runtimes directory
        source_dir = found_binary.parent
        target_dir = target_binary.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        for src_file in source_dir.iterdir():
            if src_file.is_file():
                dest_file = target_dir / src_file.name
                shutil.copy2(src_file, dest_file)

        # Step 6: set executable bit on POSIX
        if os.name != "nt" and target_binary.exists():
            target_binary.chmod(target_binary.stat().st_mode | 0o755)

        return {
            "profile_id": profile_id,
            "status": "ACQUIRED",
            "path": str(target_binary),
            "url": artifact.url,
        }
    finally:
        # Step 7: cleanup scratch directory
        if scratch_dir.exists():
            shutil.rmtree(scratch_dir, ignore_errors=True)
