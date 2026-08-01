from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.gateway.client import GatewayError, complete
from awf.registry.model_profile import (
    ModelProfileValidationError,
    load_model_profile,
    parse_model_profile,
)
from awf.secrets.store import set_secret

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "model_profiles"


def load_fixture(name: str):
    return load_model_profile(FIXTURES / name)


def test_load_local_ollama_profile():
    profile = load_fixture("local_ollama_r0.yaml")
    assert profile.purpose == "general-reasoning"
    candidate = profile.enabled_candidates_by_priority()[0]
    assert candidate.litellm_model == "ollama/phi4-mini:latest"
    assert candidate.api_base == "http://172.31.96.1:11434"


def test_parse_rejects_missing_field():
    with pytest.raises(ModelProfileValidationError):
        parse_model_profile({"purpose": "coding"})


def test_parse_rejects_invalid_purpose():
    with pytest.raises(ModelProfileValidationError):
        parse_model_profile(
            {
                "purpose": "not-a-real-purpose",
                "privacy": {"maximum_data_class": "internal", "local_only": True},
                "candidates": [{"provider": "ollama", "model": "x", "priority": 1, "enabled": True}],
                "fallback": {"mode": "none", "allow_quality_degrade": False},
                "limits": {"max_input_tokens_per_call": 1, "max_output_tokens_per_call": 1, "max_cost_usd_per_call": 0},
            }
        )


def _fake_response(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_complete_calls_litellm_with_candidate_fields(monkeypatch):
    profile = load_fixture("local_ollama_r0.yaml")
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _fake_response("pong")

    monkeypatch.setattr("awf.gateway.client.litellm.completion", fake_completion)

    result = complete(profile, [{"role": "user", "content": "ping"}])

    assert result == "pong"
    assert captured["model"] == "ollama/phi4-mini:latest"
    assert captured["api_base"] == "http://172.31.96.1:11434"
    assert captured["max_tokens"] == 256
    assert "api_key" not in captured


def test_complete_ordered_fallback_tries_next_candidate(monkeypatch):
    profile = parse_model_profile(
        {
            "purpose": "coding",
            "privacy": {"maximum_data_class": "internal", "local_only": True},
            "candidates": [
                {"provider": "ollama", "model": "broken", "priority": 1, "enabled": True},
                {"provider": "ollama", "model": "phi4-mini:latest", "priority": 2, "enabled": True},
            ],
            "fallback": {"mode": "ordered", "allow_quality_degrade": False},
            "limits": {"max_input_tokens_per_call": 1, "max_output_tokens_per_call": 1, "max_cost_usd_per_call": 0},
        }
    )
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "ollama/broken":
            raise RuntimeError("boom")
        return _fake_response("recovered")

    monkeypatch.setattr("awf.gateway.client.litellm.completion", fake_completion)

    result = complete(profile, [{"role": "user", "content": "ping"}])

    assert result == "recovered"
    assert calls == ["ollama/broken", "ollama/phi4-mini:latest"]


def test_complete_no_fallback_raises_immediately(monkeypatch):
    profile = parse_model_profile(
        {
            "purpose": "coding",
            "privacy": {"maximum_data_class": "internal", "local_only": True},
            "candidates": [
                {"provider": "ollama", "model": "broken", "priority": 1, "enabled": True},
                {"provider": "ollama", "model": "phi4-mini:latest", "priority": 2, "enabled": True},
            ],
            "fallback": {"mode": "none", "allow_quality_degrade": False},
            "limits": {"max_input_tokens_per_call": 1, "max_output_tokens_per_call": 1, "max_cost_usd_per_call": 0},
        }
    )
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs["model"])
        raise RuntimeError("boom")

    monkeypatch.setattr("awf.gateway.client.litellm.completion", fake_completion)

    with pytest.raises(RuntimeError):
        complete(profile, [{"role": "user", "content": "ping"}])

    assert calls == ["ollama/broken"]


def test_complete_resolves_api_key_from_secrets_store(tmp_path, monkeypatch):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    key = Fernet.generate_key()
    set_secret(conn, "cloud-provider-key", "sk-real-secret", key)

    profile = parse_model_profile(
        {
            "purpose": "coding",
            "privacy": {"maximum_data_class": "internal", "local_only": False},
            "candidates": [
                {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "priority": 1,
                    "enabled": True,
                    "api_key_secret_name": "cloud-provider-key",
                }
            ],
            "fallback": {"mode": "none", "allow_quality_degrade": False},
            "limits": {"max_input_tokens_per_call": 1, "max_output_tokens_per_call": 1, "max_cost_usd_per_call": 0},
        }
    )
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _fake_response("ok")

    monkeypatch.setattr("awf.gateway.client.litellm.completion", fake_completion)

    complete(profile, [{"role": "user", "content": "ping"}], conn=conn, secret_key=key)

    assert captured["api_key"] == "sk-real-secret"
    conn.close()


def test_complete_raises_when_secret_required_but_no_conn_given():
    profile = parse_model_profile(
        {
            "purpose": "coding",
            "privacy": {"maximum_data_class": "internal", "local_only": False},
            "candidates": [
                {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "priority": 1,
                    "enabled": True,
                    "api_key_secret_name": "cloud-provider-key",
                }
            ],
            "fallback": {"mode": "none", "allow_quality_degrade": False},
            "limits": {"max_input_tokens_per_call": 1, "max_output_tokens_per_call": 1, "max_cost_usd_per_call": 0},
        }
    )

    with pytest.raises(GatewayError):
        complete(profile, [{"role": "user", "content": "ping"}])
