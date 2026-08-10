"""LiteLLM Model Gateway: in-process completion calls through a Model Profile (Section 11).

No proxy process — `litellm.completion` is called directly inside the caller's
Step. Candidates are tried in priority order; a candidate's API key (when it
declares one) is resolved through the secrets store by name, never read from
the profile file itself.
"""

import json
import sqlite3
import urllib.parse
from pathlib import Path

import jsonschema
import litellm

from awf.cognition.envelope import PromptEnvelope
from awf.cognition.render import render_chat
from awf.guard.capability_guard import Decision, authorize
from awf.paths import REPO_ROOT
from awf.registry.capability_record import load_capability_record
from awf.registry.model_profile import Candidate, ModelProfile
from awf.secrets.store import get_secret

LLM_COMPLETE_CAPABILITY_REF = "llm_complete@1.0.0"


class GatewayError(RuntimeError):
    pass


def _load_llm_complete_capability(repo_root: Path = REPO_ROOT):
    return load_capability_record(repo_root / "config" / "app_registry" / "capabilities" / "llm_complete" / "1.0.0.yaml")


def _resolve_api_key(
    candidate: Candidate,
    conn: sqlite3.Connection | None,
    secret_key: bytes | None,
) -> str | None:
    if candidate.api_key_secret_name is None:
        return None
    if conn is None or secret_key is None:
        raise GatewayError(
            f"candidate '{candidate.litellm_model}' requires secret "
            f"'{candidate.api_key_secret_name}' but no secrets connection/key was provided"
        )
    return get_secret(conn, candidate.api_key_secret_name, secret_key)


def _is_loopback_api_base(api_base: str | None) -> bool:
    if not api_base:
        return False
    parsed = urllib.parse.urlparse(api_base)
    return (parsed.hostname or "") in ("127.0.0.1", "::1", "localhost")


def _is_local_candidate(candidate: Candidate) -> bool:
    return candidate.provider == "ollama" or _is_loopback_api_base(candidate.api_base)


def _authorize_completion_call(
    candidate: Candidate,
    *,
    conn: sqlite3.Connection | None,
    run_id: str | None,
    step_id: str | None,
    actor: str,
    repo_root: Path,
) -> None:
    if conn is None:
        if _is_local_candidate(candidate):
            return
        raise GatewayError("remote model completion requires a database connection and AWF run context")
    if not run_id:
        if _is_local_candidate(candidate):
            return
        raise GatewayError("remote model completion requires run_id for Capability Guard authorization")

    capability = _load_llm_complete_capability(repo_root)
    decision = authorize(
        conn,
        capability=capability,
        agent_allowlist=[capability.ref],
        run_id=run_id,
        actor=actor,
        step_id=step_id,
        payload_extra={
            "provider": candidate.provider,
            "model": candidate.model,
            "api_base": candidate.api_base,
            "loopback": _is_loopback_api_base(candidate.api_base),
        },
    )
    if decision != Decision.ALLOW:
        raise GatewayError(f"model completion blocked by Capability Guard: {decision.value}")


def _candidate_kwargs(profile: ModelProfile, candidate: Candidate, api_key: str | None) -> dict:
    kwargs: dict = {
        "model": candidate.litellm_model,
        "messages": None,
        "max_tokens": profile.limits.max_output_tokens_per_call,
    }
    if candidate.api_base:
        kwargs["api_base"] = candidate.api_base
    if api_key:
        kwargs["api_key"] = api_key
    elif candidate.provider == "openai" and _is_loopback_api_base(candidate.api_base):
        kwargs["api_key"] = "local-dev"
    return kwargs


def complete(
    profile: ModelProfile,
    messages: list[dict],
    *,
    conn: sqlite3.Connection | None = None,
    secret_key: bytes | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
    actor: str = "model-gateway",
    repo_root: Path = REPO_ROOT,
) -> str:
    candidates = profile.enabled_candidates_by_priority()
    if not candidates:
        raise GatewayError("model profile has no enabled candidates")

    last_error: Exception | None = None
    for candidate in candidates:
        _authorize_completion_call(
            candidate, conn=conn, run_id=run_id, step_id=step_id, actor=actor, repo_root=repo_root
        )
        api_key = _resolve_api_key(candidate, conn, secret_key)
        kwargs = _candidate_kwargs(profile, candidate, api_key)
        kwargs["messages"] = messages

        try:
            response = litellm.completion(**kwargs)
            return response.choices[0].message.content
        except Exception as exc:
            last_error = exc
            if profile.fallback.mode != "ordered":
                raise

    raise GatewayError(f"all candidates failed: {last_error}") from last_error


def complete_structured(
    profile: ModelProfile,
    messages: list[dict],
    *,
    schema_name: str,
    schema: dict,
    conn: sqlite3.Connection | None = None,
    secret_key: bytes | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
    actor: str = "model-gateway",
    repo_root: Path = REPO_ROOT,
) -> dict:
    candidates = profile.enabled_candidates_by_priority()
    if not candidates:
        raise GatewayError("model profile has no enabled candidates")

    last_error: Exception | None = None
    for candidate in candidates:
        _authorize_completion_call(
            candidate, conn=conn, run_id=run_id, step_id=step_id, actor=actor, repo_root=repo_root
        )
        api_key = _resolve_api_key(candidate, conn, secret_key)
        kwargs = _candidate_kwargs(profile, candidate, api_key)
        kwargs["messages"] = messages
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        }

        try:
            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                raise GatewayError("structured completion returned empty content")
            payload = json.loads(content)
            jsonschema.validate(instance=payload, schema=schema)
            return payload
        except Exception as exc:
            last_error = exc
            if profile.fallback.mode != "ordered":
                raise

    raise GatewayError(f"all candidates failed: {last_error}") from last_error


def complete_envelope(
    profile: ModelProfile,
    envelope: PromptEnvelope,
    *,
    conn: sqlite3.Connection | None = None,
    secret_key: bytes | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
    actor: str = "model-gateway",
    repo_root: Path = REPO_ROOT,
) -> str:
    chat = render_chat(envelope)
    return complete(
        profile,
        chat.messages,
        conn=conn,
        secret_key=secret_key,
        run_id=run_id,
        step_id=step_id,
        actor=actor,
        repo_root=repo_root,
    )
