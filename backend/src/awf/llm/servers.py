"""LLM Server backend definitions and configuration loader (ADR-0017)."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from awf.hardware.profiler import CANONICAL_PROFILES
from awf.paths import config_llm_dir
from awf.registry.schema import require, require_enum


class LlmServerError(ValueError):
    pass


@dataclass(frozen=True)
class Artifact:
    profile_id: str
    url: str
    archive: str  # "tar_gz" | "zip" | "manual"
    binary: str
    accelerator: str
    launch: dict


@dataclass(frozen=True)
class LlmServer:
    id: str
    managed: bool
    base_url: str
    openai_base_path: str
    provider: str
    health_paths: tuple[str, ...]
    artifacts: dict[str, Artifact]
    launch: dict
    model_defaults: dict[str, str] = field(default_factory=dict)
    api_key_secret_name: str | None = None

    @property
    def api_base(self) -> str:
        return f"{self.base_url.rstrip('/')}{self.openai_base_path}"


def load_servers(repo_root: Path) -> tuple[str, dict[str, LlmServer]]:
    servers_file = config_llm_dir(repo_root) / "servers.yaml"
    if not servers_file.is_file():
        raise LlmServerError(f"LLM servers config not found at '{servers_file}'")

    try:
        data = yaml.safe_load(servers_file.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise LlmServerError(f"Failed to parse LLM servers YAML '{servers_file}': {exc}") from exc

    if not isinstance(data, dict):
        raise LlmServerError("LLM servers config root must be a YAML mapping")

    default_server = str(require(data, "default_server", "llm_servers", error=LlmServerError))
    raw_servers = require(data, "servers", "llm_servers", error=LlmServerError)
    if not isinstance(raw_servers, dict):
        raise LlmServerError("llm_servers.servers must be a mapping")

    servers: dict[str, LlmServer] = {}
    for server_id, raw in raw_servers.items():
        ctx = f"server '{server_id}'"
        if not isinstance(raw, dict):
            raise LlmServerError(f"{ctx}: configuration must be a mapping")

        managed = bool(require(raw, "managed", ctx, error=LlmServerError))
        base_url = str(require(raw, "base_url", ctx, error=LlmServerError))
        openai_base_path = str(require(raw, "openai_base_path", ctx, error=LlmServerError))
        provider = str(require(raw, "provider", ctx, error=LlmServerError))
        raw_health = require(raw, "health_paths", ctx, error=LlmServerError)
        if not isinstance(raw_health, list):
            raise LlmServerError(f"{ctx}: health_paths must be a list")
        health_paths = tuple(str(p) for p in raw_health)
        api_key_secret_name = raw.get("api_key_secret_name")
        if api_key_secret_name is not None:
            api_key_secret_name = str(api_key_secret_name)

        server_launch = raw.get("launch") or {}
        if not isinstance(server_launch, dict):
            raise LlmServerError(f"{ctx}: launch must be a mapping")
        model_defaults = raw.get("model_defaults") or {}
        if not isinstance(model_defaults, dict):
            raise LlmServerError(f"{ctx}: model_defaults must be a mapping")
        for profile_id in model_defaults:
            if profile_id not in CANONICAL_PROFILES:
                raise LlmServerError(
                    f"{ctx}: model_defaults key '{profile_id}' is not a valid canonical profile ID in {CANONICAL_PROFILES}"
                )

        raw_artifacts = raw.get("artifacts") or {}
        if not isinstance(raw_artifacts, dict):
            raise LlmServerError(f"{ctx}: artifacts must be a mapping")

        artifacts: dict[str, Artifact] = {}
        for art_profile_id, art_raw in raw_artifacts.items():
            if art_profile_id not in CANONICAL_PROFILES:
                raise LlmServerError(
                    f"{ctx}: artifact key '{art_profile_id}' is not a valid canonical profile ID in {CANONICAL_PROFILES}"
                )

            art_ctx = f"{ctx}.artifacts.{art_profile_id}"
            if not isinstance(art_raw, dict):
                raise LlmServerError(f"{art_ctx}: artifact configuration must be a mapping")

            url = str(require(art_raw, "url", art_ctx, error=LlmServerError))
            archive = require_enum(
                require(art_raw, "archive", art_ctx, error=LlmServerError),
                ("tar_gz", "zip", "manual"),
                art_ctx,
                error=LlmServerError,
            )
            binary = str(require(art_raw, "binary", art_ctx, error=LlmServerError))
            accelerator = require_enum(
                require(art_raw, "accelerator", art_ctx, error=LlmServerError),
                ("cpu", "gpu.cuda", "gpu.vulkan", "npu.qnn", "gpu.opencl.adreno"),
                art_ctx,
                error=LlmServerError,
            )
            art_launch = art_raw.get("launch") or {}
            if not isinstance(art_launch, dict):
                raise LlmServerError(f"{art_ctx}: launch must be a mapping")

            merged_art_launch = {**server_launch, **art_launch}
            artifacts[art_profile_id] = Artifact(
                profile_id=art_profile_id,
                url=url,
                archive=archive,
                binary=binary,
                accelerator=accelerator,
                launch=merged_art_launch,
            )

        servers[server_id] = LlmServer(
            id=server_id,
            managed=managed,
            base_url=base_url,
            openai_base_path=openai_base_path,
            provider=provider,
            health_paths=health_paths,
            artifacts=artifacts,
            launch=server_launch,
            model_defaults={str(k): str(v) for k, v in model_defaults.items()},
            api_key_secret_name=api_key_secret_name,
        )

    if default_server not in servers:
        raise LlmServerError(f"default_server '{default_server}' is not declared in servers mapping")

    return default_server, servers


def artifact_for(server: LlmServer, profile_id: str) -> Artifact | None:
    return server.artifacts.get(profile_id)
