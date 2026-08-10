"""LLM Model Profile selection and publishing for Resident Mind (ADR-0017)."""

import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from awf.cli.core_ops import op_registry_publish
from awf.hardware.profiler import resolve_hardware_profile_id
from awf.llm.discovery import local_models, model_by_name
from awf.llm.servers import LlmServerError, load_servers
from awf.registry.resolve import resolve_registry_object

RESIDENT_MIND_NAME = "resident-mind"
RESIDENT_MIND_VERSION = "1.0.0"


@dataclass(frozen=True)
class Selection:
    server_id: str
    provider: str
    model: str
    api_base: str
    local_only: bool
    api_key_secret_name: str | None


def current_selection(repo_root: Path) -> Selection | None:
    try:
        path, _source = resolve_registry_object(repo_root, "model-profiles", RESIDENT_MIND_NAME, RESIDENT_MIND_VERSION)
    except Exception:
        return None

    if not path.is_file():
        return None

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    candidates = data.get("candidates") or []
    if not candidates or not isinstance(candidates, list):
        return None

    cand = candidates[0]
    if not isinstance(cand, dict):
        return None

    provider = str(cand.get("provider", "openai"))
    model = str(cand.get("model", ""))
    api_base = str(cand.get("api_base", ""))
    api_key_secret_name = cand.get("api_key_secret_name")

    privacy = data.get("privacy") or {}
    local_only = bool(privacy.get("local_only", True))

    explicit_server_id = data.get("server_id") or cand.get("server_id")
    if explicit_server_id:
        server_id = str(explicit_server_id)
    else:
        server_id = "llama-server"
        try:
            _, servers = load_servers(repo_root)
            for s_id, s in servers.items():
                if s.api_base == api_base or (not s.managed and s.provider == provider):
                    server_id = s_id
                    break
        except Exception:
            pass

    return Selection(
        server_id=server_id,
        provider=provider,
        model=model,
        api_base=api_base,
        local_only=local_only,
        api_key_secret_name=api_key_secret_name,
    )


def select(
    repo_root: Path,
    conn: Any,
    *,
    server_id: str,
    model: str | None = None,
    allow_remote: bool = False,
) -> dict:
    _, servers = load_servers(repo_root)
    if server_id not in servers:
        raise LlmServerError(f"Unknown server ID '{server_id}'. Available: {sorted(servers.keys())}")

    server = servers[server_id]

    if server.managed:
        if model is not None:
            lm = model_by_name(repo_root, model)
            model_name = lm.primary.name
        elif server.model_defaults:
            profile_id, _payload = resolve_hardware_profile_id(repo_root)
            default_model = server.model_defaults.get(profile_id)
            if default_model is None:
                os_name, arch, _suffix = profile_id.rsplit("-", 2)
                default_model = server.model_defaults.get(f"{os_name}-{arch}-cpu")
            if default_model is None:
                default_model = next(iter(server.model_defaults.values()))
            lm = model_by_name(repo_root, default_model)
            model_name = lm.primary.name
        else:
            avail = local_models(repo_root)
            if not avail:
                raise LlmServerError("No local models found under models/llm/ and no --model argument supplied")
            model_name = avail[0].primary.name
    else:
        if model is not None:
            model_name = model
        else:
            model_name = "default"

    parsed_url = urllib.parse.urlparse(server.base_url)
    hostname = parsed_url.hostname or ""
    is_loopback = hostname in ("127.0.0.1", "::1", "localhost")
    local_only = is_loopback

    if not is_loopback and not allow_remote:
        raise LlmServerError(
            f"Server base_url '{server.base_url}' points to non-loopback host '{hostname}'; pass --allow-remote to permit remote endpoints"
        )

    candidate: dict[str, Any] = {
        "provider": server.provider,
        "model": model_name,
        "priority": 1,
        "enabled": True,
        "api_base": server.api_base,
        "server_id": server_id,
    }
    if server.api_key_secret_name:
        candidate["api_key_secret_name"] = server.api_key_secret_name

    profile_data = {
        "name": RESIDENT_MIND_NAME,
        "version": RESIDENT_MIND_VERSION,
        "purpose": "general-reasoning",
        "server_id": server_id,
        "privacy": {"maximum_data_class": "internal", "local_only": local_only},
        "candidates": [candidate],
        "fallback": {"mode": "none", "allow_quality_degrade": False},
        "limits": {
            "max_input_tokens_per_call": 8192,
            "max_output_tokens_per_call": 1024,
            "max_cost_usd_per_call": 0.0,
        },
    }

    yaml_text = yaml.dump(profile_data, sort_keys=False)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        tf.write(yaml_text)
        temp_path = Path(tf.name)

    try:
        pub_result = op_registry_publish(repo_root, conn, path=temp_path, kind="model-profiles")
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return {
        "server_id": server_id,
        "model": model_name,
        "profile_ref": f"{RESIDENT_MIND_NAME}@{RESIDENT_MIND_VERSION}",
        "local_only": local_only,
        "publish": pub_result,
    }
