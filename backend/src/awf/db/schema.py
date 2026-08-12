"""SQLite schema for data/awf_db/awf.db — Section 8 of the AWF spec.

Column shapes are the contract; this module is one conforming realization of it.
"""

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        workflow_ref TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN (
            'CREATED', 'VALIDATING', 'QUEUED', 'RUNNING',
            'WAITING_INPUT', 'WAITING_APPROVAL',
            'SUCCEEDED', 'FAILED', 'CANCELING', 'CANCELED'
        )),
        input_json TEXT NOT NULL,
        output_json TEXT,
        budget_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS steps (
        step_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs (run_id),
        node_id TEXT NOT NULL,
        attempt INTEGER NOT NULL,
        status TEXT NOT NULL CHECK (status IN (
            'PENDING', 'READY', 'RUNNING', 'WAITING_INPUT', 'WAITING_APPROVAL',
            'RETRY_WAIT', 'SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELED'
        )),
        input_json TEXT NOT NULL,
        output_json TEXT,
        failure_class TEXT CHECK (failure_class IS NULL OR failure_class IN (
            'TRANSIENT', 'TIMEOUT', 'INVALID_INPUT', 'POLICY_DENIED',
            'APPROVAL_REJECTED', 'TOOL_ERROR', 'SANDBOX_VIOLATION',
            'NONDETERMINISTIC_OUTPUT', 'INTEGRITY_FAILURE',
            'UNKNOWN_SIDE_EFFECT', 'INTERNAL'
        )),
        started_at TEXT NOT NULL,
        ended_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_steps_run_id ON steps (run_id)",
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs (run_id),
        step_id TEXT REFERENCES steps (step_id),
        attempt INTEGER,
        prior_status TEXT,
        new_status TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        actor TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_run_id ON events (run_id)",
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs (run_id),
        step_id TEXT NOT NULL REFERENCES steps (step_id),
        sha256 TEXT NOT NULL,
        relative_path TEXT NOT NULL,
        media_type TEXT NOT NULL,
        artifact_type TEXT NOT NULL CHECK (artifact_type IN (
            'candidate', 'plan', 'patch', 'report', 'test-result', 'finding', 'verdict'
        )),
        complete INTEGER NOT NULL DEFAULT 0 CHECK (complete IN (0, 1)),
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts (run_id)",
    """
    CREATE TABLE IF NOT EXISTS approvals (
        approval_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs (run_id),
        step_id TEXT NOT NULL REFERENCES steps (step_id),
        action_digest TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
        reason TEXT,
        requested_at TEXT NOT NULL,
        decided_at TEXT,
        risk_class TEXT CHECK (risk_class IS NULL OR risk_class IN ('R0', 'R1', 'R2', 'R3'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_approvals_run_id ON approvals (run_id)",
    """
    CREATE TABLE IF NOT EXISTS secrets (
        name TEXT PRIMARY KEY,
        ciphertext BLOB NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS registry_index (
        kind TEXT NOT NULL,
        name TEXT NOT NULL,
        version TEXT NOT NULL,
        digest TEXT NOT NULL,
        source TEXT NOT NULL CHECK (source IN ('config', 'data')),
        path TEXT NOT NULL,
        trust_status TEXT CHECK (trust_status IS NULL OR trust_status IN (
            'local', 'trusted', 'quarantined', 'blocked'
        )),
        indexed_at TEXT NOT NULL,
        PRIMARY KEY (kind, name, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS registry_proposals (
        proposal_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('workflows', 'semantic-memories')),
        name TEXT NOT NULL,
        version TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'rejected')),
        draft_digest TEXT NOT NULL,
        draft_path TEXT NOT NULL,
        summary TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        decided_at TEXT,
        published_digest TEXT,
        rejection_reason TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS registry_proposal_events (
        event_id TEXT PRIMARY KEY,
        proposal_id TEXT NOT NULL REFERENCES registry_proposals (proposal_id),
        event_type TEXT NOT NULL CHECK (event_type IN ('created', 'updated', 'verified', 'published', 'rejected')),
        occurred_at TEXT NOT NULL,
        actor TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_registry_proposal_events_proposal_id ON registry_proposal_events (proposal_id)",
    """
    CREATE TABLE IF NOT EXISTS improvement_proposals (
        improvement_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs (run_id),
        target_repo TEXT NOT NULL,
        target_branch TEXT NOT NULL,
        base_commit TEXT NOT NULL,
        candidate_branch TEXT NOT NULL,
        candidate_commit TEXT NOT NULL,
        diff_digest TEXT NOT NULL,
        patch_artifact_id TEXT NOT NULL REFERENCES artifacts (artifact_id),
        status TEXT NOT NULL CHECK (
            status IN ('draft', 'ready_for_review', 'approved', 'merged', 'rejected', 'abandoned')
        ),
        summary TEXT NOT NULL,
        changed_paths_json TEXT NOT NULL,
        verdict_artifact_id TEXT,
        validation_artifact_ids_json TEXT NOT NULL,
        merge_commit TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        decided_at TEXT,
        closed_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_improvement_proposals_run_id ON improvement_proposals (run_id)",
    """
    CREATE TABLE IF NOT EXISTS improvement_proposal_events (
        event_id TEXT PRIMARY KEY,
        improvement_id TEXT NOT NULL REFERENCES improvement_proposals (improvement_id),
        event_type TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        actor TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_improvement_proposal_events_id ON improvement_proposal_events (improvement_id)",
    """
    CREATE TABLE IF NOT EXISTS active_sessions (
        session_id TEXT PRIMARY KEY,
        title TEXT,
        status TEXT NOT NULL CHECK (status IN ('active', 'summarized', 'expired')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        expires_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS active_session_entries (
        entry_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES active_sessions (session_id),
        role TEXT NOT NULL CHECK (role IN ('operator', 'assistant', 'system', 'tool')),
        content_json TEXT NOT NULL,
        summary TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_active_session_entries_session_id ON active_session_entries (session_id)",
]

EXPECTED_TABLES = (
    "runs",
    "steps",
    "events",
    "artifacts",
    "approvals",
    "secrets",
    "registry_index",
    "registry_proposals",
    "registry_proposal_events",
    "improvement_proposals",
    "improvement_proposal_events",
    "active_sessions",
    "active_session_entries",
)
