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
        decided_at TEXT
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
        path TEXT NOT NULL,
        trust_status TEXT NOT NULL CHECK (trust_status IN (
            'local', 'trusted', 'quarantined', 'blocked'
        )),
        indexed_at TEXT NOT NULL,
        PRIMARY KEY (kind, name, version)
    )
    """,
]

EXPECTED_TABLES = (
    "runs",
    "steps",
    "events",
    "artifacts",
    "approvals",
    "secrets",
    "registry_index",
)
