"""LLM server registry object loader (ADR-0017)."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from awf.hardware.profiler import CANONICAL_PROFILES
from awf.paths import config_registry_dir
from awf.registry.schema import validate_json_schema, validate_registry_identity
from awf.registry.schemas.llm_servers import NAME, SCHEMA, VERSION


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


def resolve_servers_path(repo_root: Path) -> Path:
    return config_registry_dir(repo_root) / "llm-servers" / NAME / f"{VERSION}.yaml"


def parse_servers(data: dict) -> tuple[str, dict[str, LlmServer]]:
    validate_json_schema(data, SCHEMA, "llm servers", error=LlmServerError)
    metadata = data["metadata"]
    spec = data["spec"]

    default_server = spec["default_server"]
    raw_servers = spec["servers"]

    servers: dict[str, LlmServer] = {}
    for server_id, raw in raw_servers.items():
        ctx = f"server '{server_id}'"
        raw_health = raw["health_paths"]
        api_key_secret_name = raw.get("api_key_secret_name")

        server_launch = raw.get("launch") or {}
        model_defaults = raw.get("model_defaults") or {}
        for profile_id in model_defaults:
            if profile_id not in CANONICAL_PROFILES:
                raise LlmServerError(
                    f"{ctx}: model_defaults key '{profile_id}' is not a valid canonical profile ID in {CANONICAL_PROFILES}"
                )

        raw_artifacts = raw.get("artifacts") or {}

        artifacts: dict[str, Artifact] = {}
        for art_profile_id, art_raw in raw_artifacts.items():
            if art_profile_id not in CANONICAL_PROFILES:
                raise LlmServerError(
                    f"{ctx}: artifact key '{art_profile_id}' is not a valid canonical profile ID in {CANONICAL_PROFILES}"
                )

            art_launch = art_raw.get("launch") or {}
            merged_art_launch = {**server_launch, **art_launch}
            artifacts[art_profile_id] = Artifact(
                profile_id=art_profile_id,
                url=art_raw["url"],
                archive=art_raw["archive"],
                binary=art_raw["binary"],
                accelerator=art_raw["accelerator"],
                launch=merged_art_launch,
            )

        servers[server_id] = LlmServer(
            id=server_id,
            managed=raw["managed"],
            base_url=raw["base_url"],
            openai_base_path=raw["openai_base_path"],
            provider=raw["provider"],
            health_paths=tuple(raw_health),
            artifacts=artifacts,
            launch=server_launch,
            model_defaults={str(k): str(v) for k, v in model_defaults.items()},
            api_key_secret_name=api_key_secret_name,
        )

    if default_server not in servers:
        raise LlmServerError(f"default_server '{default_server}' is not declared in servers mapping")

    if metadata["name"] != NAME:
        raise LlmServerError(f"llm servers metadata.name must be '{NAME}'")

    return default_server, servers


def load_servers_file(servers_file: Path) -> tuple[str, dict[str, LlmServer]]:
    if not servers_file.is_file():
        raise LlmServerError(f"LLM servers config not found at '{servers_file}'")

    try:
        data = yaml.safe_load(servers_file.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise LlmServerError(f"Failed to parse LLM servers YAML '{servers_file}': {exc}") from exc

    if not isinstance(data, dict):
        raise LlmServerError("LLM servers config root must be a YAML mapping")

    default_server, servers = parse_servers(data)
    validate_registry_identity(
        name=data["metadata"]["name"],
        version=data["metadata"]["version"],
        path=servers_file,
        context="llm servers",
        error=LlmServerError,
    )

    return default_server, servers


def load_servers(repo_root: Path) -> tuple[str, dict[str, LlmServer]]:
    return load_servers_file(resolve_servers_path(repo_root))


def artifact_for(server: LlmServer, profile_id: str) -> Artifact | None:
    return server.artifacts.get(profile_id)
