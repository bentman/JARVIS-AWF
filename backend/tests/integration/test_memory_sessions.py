from backend.tests.support import make_awf_repo

from awf.cli.core_ops import op_session_append, op_session_show, op_session_start, op_session_summarize


def test_active_session_lifecycle(tmp_path):
    _repo_root, conn = make_awf_repo(tmp_path)

    session = op_session_start(conn, title="demo")
    entry = op_session_append(
        conn,
        session_id=session["session_id"],
        role="operator",
        content={"text": "remember targeted tests"},
        summary="targeted tests",
    )
    shown = op_session_show(conn, session_id=session["session_id"])
    summarized = op_session_summarize(conn, session_id=session["session_id"], summary="done")

    assert entry["entries"][0]["role"] == "operator"
    assert shown["entries"][0]["content"] == {"text": "remember targeted tests"}
    assert summarized["status"] == "summarized"
