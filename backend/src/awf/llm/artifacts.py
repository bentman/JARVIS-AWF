"""Managed LLM artifact selection."""

from pathlib import Path


def cpu_fallback_profile_id(profile_id: str) -> str:
    os_name, arch, _suffix = profile_id.rsplit("-", 2)
    return f"{os_name}-{arch}-cpu"


def artifact_binary_present(repo_root: Path, profile_id: str, artifact) -> bool:
    from awf.llm.discovery import binary_path

    path = binary_path(repo_root, profile_id, artifact)
    return path.is_file() and path.stat().st_size > 0


def select_managed_llm_artifact(repo_root: Path, server, profile_id: str, *, allow_cpu_fallback: bool = True):
    from awf.llm.servers import artifact_for

    artifact = artifact_for(server, profile_id)
    if artifact is not None and artifact_binary_present(repo_root, profile_id, artifact):
        return profile_id, artifact

    if allow_cpu_fallback:
        cpu_profile_id = cpu_fallback_profile_id(profile_id)
        cpu_artifact = artifact_for(server, cpu_profile_id)
        if cpu_artifact is not None and artifact_binary_present(repo_root, cpu_profile_id, cpu_artifact):
            return cpu_profile_id, cpu_artifact

    return profile_id, artifact
