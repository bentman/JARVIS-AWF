from awf.machine.action import MachineAction, content_digest


def test_machine_action_digest_is_canonical_and_content_digest_omits_raw_body():
    first = MachineAction(
        kind="fs_write",
        run_id="run-1",
        step_id="step-1",
        node_id="write",
        operation="update",
        capability_ref="fs_write@1.0.0",
        risk_class="R1",
        approval="per-invocation",
        target={"path": "/worktree/a.txt"},
        body_digest=content_digest("hello"),
    )
    second = MachineAction(
        kind="fs_write",
        run_id="run-1",
        step_id="step-1",
        node_id="write",
        operation="update",
        capability_ref="fs_write@1.0.0",
        risk_class="R1",
        approval="per-invocation",
        target={"path": "/worktree/a.txt"},
        body_digest=content_digest("hello"),
    )

    assert first.digest == second.digest
    payload = first.to_dict()
    assert payload["body_digest"].startswith("sha256:")
    assert "hello" not in str(payload)
