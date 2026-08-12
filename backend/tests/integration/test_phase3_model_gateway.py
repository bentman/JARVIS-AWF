import json
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from awf.cognition.envelope import PromptEnvelope, PromptSegment
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.gateway.client import GatewayError, complete, complete_envelope, complete_structured
from awf.gateway.client import HOSTED_LLM_COMPLETE_CAPABILITY_REF, LLM_COMPLETE_CAPABILITY_REF
from awf.registry.model_profile import (
    ModelProfileValidationError,
    load_model_profile,
    parse_model_profile,
)
from awf.secrets.store import set_secret

EXAMPLE_PROFILE_NAMES = (
    "example-ollama-general",
    "example-llamacpp-coding",
    "example-lmstudio-embedding",
    "example-anthropic-judge",
    "example-openai-adversary",
    "resident-mind",
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


def _seed_run(conn, run_id: str = "run-1") -> None:
    conn.execute(
        "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
        "VALUES (?, 'wf@1.0.0#sha256:abc', 'RUNNING', '{}', '{}', 't', 't')",
        (run_id,),
    )
    conn.commit()


def test_complete_calls_litellm_with_candidate_fields(monkeypatch, repo_root):
    profile = load_example_profile(repo_root, "example-ollama-general")
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _fake_response("pong")

    monkeypatch.setattr("awf.gateway.client._litellm_completion", fake_completion)

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

    monkeypatch.setattr("awf.gateway.client._litellm_completion", fake_completion)

    assert complete(profile, [{"role": "user", "content": "ping"}]) == "ok"
    assert captured["api_key"] == "local-dev"


def test_complete_structured_passes_json_schema_and_validates_response(monkeypatch):
    profile = parse_model_profile(
        {
            "name": "demo",
            "version": "1.0.0",
            "purpose": "general-reasoning",
            "privacy": {"maximum_data_class": "internal", "local_only": True},
            "candidates": [
                {
                    "provider": "openai",
                    "model": "local",
                    "priority": 1,
                    "enabled": True,
                    "api_base": "http://127.0.0.1:8080/v1",
                }
            ],
            "fallback": {"mode": "none", "allow_quality_degrade": False},
            "limits": {"max_input_tokens_per_call": 1, "max_output_tokens_per_call": 1, "max_cost_usd_per_call": 0},
        }
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _fake_response('{"answer": "ok"}')

    monkeypatch.setattr("awf.gateway.client._litellm_completion", fake_completion)

    result = complete_structured(profile, [{"role": "user", "content": "ping"}], schema_name="demo_schema", schema=schema)

    assert result == {"answer": "ok"}
    assert captured["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "demo_schema", "schema": schema, "strict": True},
    }
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

    monkeypatch.setattr("awf.gateway.client._litellm_completion", fake_completion)

    with pytest.raises(GatewayError, match="remote model completion requires"):
        complete(profile, [{"role": "user", "content": "ping"}])
    assert captured == {}


def test_complete_records_local_model_call_when_run_context_is_present(monkeypatch, tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    _seed_run(conn)
    profile = parse_model_profile(
        {
            "name": "demo",
            "version": "1.0.0",
            "purpose": "general-reasoning",
            "privacy": {"maximum_data_class": "internal", "local_only": True},
            "candidates": [
                {
                    "provider": "openai",
                    "model": "local",
                    "priority": 1,
                    "enabled": True,
                    "api_base": "http://127.0.0.1:8080/v1",
                }
            ],
            "fallback": {"mode": "none", "allow_quality_degrade": False},
            "limits": {"max_input_tokens_per_call": 1, "max_output_tokens_per_call": 1, "max_cost_usd_per_call": 0},
        }
    )

    monkeypatch.setattr("awf.gateway.client._litellm_completion", lambda **_kwargs: _fake_response("ok"))

    assert complete(profile, [{"role": "user", "content": "ping"}], conn=conn, run_id="run-1") == "ok"
    row = conn.execute("SELECT new_status, reason_code, payload_json FROM events WHERE run_id = 'run-1'").fetchone()
    assert row["new_status"] == "allow"
    assert row["reason_code"] == "approval_never"
    payload = json.loads(row["payload_json"])
    assert payload["capability_ref"] == LLM_COMPLETE_CAPABILITY_REF
    assert payload["loopback"] is True
    conn.close()


def test_complete_requires_hosted_llm_risk_decision_before_remote_call(monkeypatch, tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    _seed_run(conn)
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

    monkeypatch.setattr("awf.gateway.client._litellm_completion", fake_completion)

    with pytest.raises(GatewayError, match="approval_required"):
        complete(
            profile,
            [{"role": "user", "content": "ping"}],
            conn=conn,
            run_id="run-1",
            agent_allowlist=[HOSTED_LLM_COMPLETE_CAPABILITY_REF],
        )
    assert captured == {}
    row = conn.execute("SELECT new_status, reason_code, payload_json FROM events WHERE run_id = 'run-1'").fetchone()
    assert row["new_status"] == "approval_required"
    assert row["reason_code"] == "approval_per_invocation"
    payload = json.loads(row["payload_json"])
    assert payload["capability_ref"] == HOSTED_LLM_COMPLETE_CAPABILITY_REF
    assert payload["api_base"] == "https://api.example.test/v1"
    assert payload["loopback"] is False
    conn.close()


def test_remote_model_call_is_denied_without_hosted_allowlist(monkeypatch, tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    _seed_run(conn)
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

    monkeypatch.setattr("awf.gateway.client._litellm_completion", fake_completion)

    with pytest.raises(GatewayError, match="deny"):
        complete(profile, [{"role": "user", "content": "ping"}], conn=conn, run_id="run-1")
    assert captured == {}
    row = conn.execute("SELECT new_status, reason_code, payload_json FROM events WHERE run_id = 'run-1'").fetchone()
    assert row["new_status"] == "deny"
    assert row["reason_code"] == "not_in_agent_allowlist"
    assert json.loads(row["payload_json"])["capability_ref"] == HOSTED_LLM_COMPLETE_CAPABILITY_REF
    conn.close()


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

    monkeypatch.setattr("awf.gateway.client._litellm_completion", fake_completion)

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

    monkeypatch.setattr("awf.gateway.client._litellm_completion", fake_completion)

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

    monkeypatch.setattr("awf.gateway.client._litellm_completion", fake_completion)

    with pytest.raises(RuntimeError):
        complete(profile, [{"role": "user", "content": "ping"}])

    assert calls == ["ollama/broken"]


def test_complete_resolves_api_key_from_secrets_store(tmp_path, monkeypatch):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    _seed_run(conn)
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

    monkeypatch.setattr("awf.gateway.client._litellm_completion", fake_completion)

    with pytest.raises(GatewayError, match="approval_required"):
        complete(
            profile,
            [{"role": "user", "content": "ping"}],
            conn=conn,
            secret_key=key,
            run_id="run-1",
            agent_allowlist=[HOSTED_LLM_COMPLETE_CAPABILITY_REF],
        )

    assert captured == {}
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
