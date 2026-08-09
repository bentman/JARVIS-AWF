"""LiteLLM Model Gateway: in-process completion calls through a Model Profile (Section 11).

No proxy process — `litellm.completion` is called directly inside the caller's
Step. Candidates are tried in priority order; a candidate's API key (when it
declares one) is resolved through the secrets store by name, never read from
the profile file itself.
"""

import json
import sqlite3
import urllib.parse

import jsonschema
import litellm

from awf.cognition.envelope import PromptEnvelope
from awf.cognition.render import render_chat
from awf.registry.model_profile import Candidate, ModelProfile
from awf.secrets.store import get_secret


class GatewayError(RuntimeError):
    pass


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


def complete(
    profile: ModelProfile,
    messages: list[dict],
    *,
    conn: sqlite3.Connection | None = None,
    secret_key: bytes | None = None,
) -> str:
    candidates = profile.enabled_candidates_by_priority()
    if not candidates:
        raise GatewayError("model profile has no enabled candidates")

    last_error: Exception | None = None
    for candidate in candidates:
        api_key = _resolve_api_key(candidate, conn, secret_key)
        kwargs: dict = {
            "model": candidate.litellm_model,
            "messages": messages,
            "max_tokens": profile.limits.max_output_tokens_per_call,
        }
        if candidate.api_base:
            kwargs["api_base"] = candidate.api_base
        if api_key:
            kwargs["api_key"] = api_key
        elif candidate.provider == "openai" and _is_loopback_api_base(candidate.api_base):
            kwargs["api_key"] = "local-dev"

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
) -> dict:
    candidates = profile.enabled_candidates_by_priority()
    if not candidates:
        raise GatewayError("model profile has no enabled candidates")

    last_error: Exception | None = None
    for candidate in candidates:
        api_key = _resolve_api_key(candidate, conn, secret_key)
        kwargs: dict = {
            "model": candidate.litellm_model,
            "messages": messages,
            "max_tokens": profile.limits.max_output_tokens_per_call,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                },
            },
        }
        if candidate.api_base:
            kwargs["api_base"] = candidate.api_base
        if api_key:
            kwargs["api_key"] = api_key
        elif candidate.provider == "openai" and _is_loopback_api_base(candidate.api_base):
            kwargs["api_key"] = "local-dev"

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
) -> str:
    chat = render_chat(envelope)
    return complete(profile, chat.messages, conn=conn, secret_key=secret_key)
