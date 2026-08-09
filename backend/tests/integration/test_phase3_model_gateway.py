from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from awf.cognition.envelope import PromptEnvelope, PromptSegment
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.gateway.client import GatewayError, complete, complete_envelope
from awf.registry.model_profile import (
    ModelProfileValidationError,
    load_model_profile,
    parse_model_profile,
)
from awf.secrets.store import set_secret

# ADR-0001: these are reference examples, never resolved by a real Run
# (registry/resolve.py::DATA_ONLY_KINDS) - tests load them directly by path.
EXAMPLE_PROFILE_NAMES = (
    "example-ollama-general",
    "example-llamacpp-coding",
    "example-lmstudio-embedding",
    "example-anthropic-judge",
    "example-openai-adversary",
)


def load_example_profile(repo_root, name: str, version: str = "1.0.0"):
    examples_root = repo_root / "config" / "app_registry" / "model-profiles"
    return load_model_profile(examples_root / name / f"{version}.yaml")


@pytest.mark.parametrize("name", EXAMPLE_PROFILE_NAMES)
def test_every_example_profile_parses(name, repo_root):
    profile = load_example_profile(repo_root, name)
    assert profile.enabled_candidates_by_priority()


def test_load_example_ollama_general_reasoning_profile(repo_root):
    profile = load_example_profile(repo_root, "example-ollama-general")
    assert profile.purpose == "general-reasoning"
    candidate = profile.enabled_candidates_by_priority()[0]
    assert candidate.litellm_model == "ollama/phi4-mini:latest"
    assert candidate.api_base == "http://localhost:11434"


def test_example_judge_and_adversary_profiles_use_different_provider_families(repo_root):
    # Section 12.3: Adversary MUST resolve to a different model family than
    # the Builder; these two examples demonstrate that pairing.
    judge = load_example_profile(repo_root, "example-anthropic-judge")
    adversary = load_example_profile(repo_root, "example-openai-adversary")
    judge_candidate = judge.enabled_candidates_by_priority()[0]
    adversary_candidate = adversary.enabled_candidates_by_priority()[0]
    assert judge_candidate.provider != adversary_candidate.provider


def test_parse_rejects_missing_field():
    with pytest.raises(ModelProfileValidationError):
        parse_model_profile({"purpose": "coding"})


def test_parse_rejects_invalid_purpose():
    with pytest.raises(ModelProfileValidationError):
        parse_model_profile(
            {
                "name": "demo",
                "version": "1.0.0",
                "purpose": "not-a-real-purpose",
                "privacy": {"maximum_data_class": "internal", "local_only": True},
                "candidates": [{"provider": "ollama", "model": "x", "priority": 1, "enabled": True}],
                "fallback": {"mode": "none", "allow_quality_degrade": False},
                "limits": {"max_input_tokens_per_call": 1, "max_output_tokens_per_call": 1, "max_cost_usd_per_call": 0},
            }
        )


def _fake_response(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_complete_calls_litellm_with_candidate_fields(monkeypatch, repo_root):
    profile = load_example_profile(repo_root, "example-ollama-general")
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _fake_response("pong")

    monkeypatch.setattr("awf.gateway.client.litellm.completion", fake_completion)

    result = complete(profile, [{"role": "user", "content": "ping"}])

    assert result == "pong"
    assert captured["model"] == "ollama/phi4-mini:latest"
    assert captured["api_base"] == "http://localhost:11434"
    assert captured["max_tokens"] == 256
    assert "api_key" not in captured


def test_complete_supplies_dummy_api_key_for_loopback_openai_compatible(monkeypatch):
    profile = parse_model_profile(
        {
            "name": "demo",
            "version": "1.0.0",
            "purpose": "general-reasoning",
            "privacy": {"maximum_data_class": "internal", "local_only": True},
            "candidates": [
                {
                    "provider": "openai",
                    "model": "Qwen3-8B-Q5_K_M.gguf",
                    "priority": 1,
                    "enabled": True,
                    "api_base": "http://127.0.0.1:8080/v1",
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

    assert complete(profile, [{"role": "user", "content": "ping"}]) == "ok"
    assert captured["api_key"] == "local-dev"


def test_complete_does_not_supply_dummy_api_key_for_remote_openai(monkeypatch):
    profile = parse_model_profile(
        {
            "name": "demo",
            "version": "1.0.0",
            "purpose": "general-reasoning",
            "privacy": {"maximum_data_class": "internal", "local_only": False},
            "candidates": [
                {
                    "provider": "openai",
                    "model": "gpt-demo",
                    "priority": 1,
                    "enabled": True,
                    "api_base": "https://api.example.test/v1",
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

    assert complete(profile, [{"role": "user", "content": "ping"}]) == "ok"
    assert "api_key" not in captured


def test_complete_envelope_renders_chat_and_model_profile_bounds_max_tokens(monkeypatch, repo_root):
    profile = load_example_profile(repo_root, "example-ollama-general")
    envelope = PromptEnvelope(
        segments=(
            PromptSegment("persona", "style", True, "Persona asks for 9999 max tokens."),
            PromptSegment("skill", "instruction", False, "Skill body."),
            PromptSegment("user", "input", False, "ping"),
        ),
        generation={"max_tokens": 9999},
    )
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _fake_response("pong")

    monkeypatch.setattr("awf.gateway.client.litellm.completion", fake_completion)

    result = complete_envelope(profile, envelope)

    assert result == "pong"
    assert captured["max_tokens"] == profile.limits.max_output_tokens_per_call
    assert captured["messages"][0]["role"] == "system"
    assert "[persona/style]\nPersona asks for 9999 max tokens." in captured["messages"][0]["content"]
    assert captured["messages"][-1]["role"] == "user"
    assert "[skill/instruction, untrusted]\nSkill body." in captured["messages"][-1]["content"]


def test_complete_ordered_fallback_tries_next_candidate(monkeypatch):
    profile = parse_model_profile(
        {
            "name": "demo",
            "version": "1.0.0",
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
            "name": "demo",
            "version": "1.0.0",
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
            "name": "demo",
            "version": "1.0.0",
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
            "name": "demo",
            "version": "1.0.0",
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
