import React, { useState } from "react";

export interface MemorySearchHit {
  ref: string;
  score: number;
  confidence: number;
  object: Record<string, unknown>;
}

export interface MemorySearchResult {
  semantic: MemorySearchHit[];
  episodic: Record<string, unknown>[];
}

export interface MemoryPanelProps {
  onMemorySearch: (query: string) => Promise<MemorySearchResult>;
  onMemoryBlock: (ref: string) => Promise<unknown>;
  onMemoryPublish: (proposalId: string, digest: string) => Promise<unknown>;
  onMemoryReject: (proposalId: string, reason?: string) => Promise<unknown>;
}

export function MemoryPanel({
  onMemorySearch,
  onMemoryBlock,
  onMemoryPublish,
  onMemoryReject,
}: MemoryPanelProps): React.JSX.Element {
  const [query, setQuery] = useState("");
  const [proposalId, setProposalId] = useState("");
  const [digest, setDigest] = useState("");
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<MemorySearchResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const search = async () => {
    const next = await onMemorySearch(query);
    setResult(next);
    setMessage(`found ${next.semantic.length} semantic and ${next.episodic.length} episodic matches`);
  };

  const publish = async () => {
    await onMemoryPublish(proposalId, digest);
    setMessage(`published ${proposalId}`);
  };

  const reject = async () => {
    await onMemoryReject(proposalId, reason || undefined);
    setMessage(`rejected ${proposalId}`);
  };

  const block = async (ref: string) => {
    await onMemoryBlock(ref);
    setMessage(`blocked ${ref}`);
  };

  return (
    <section aria-label="memory" className="card">
      <div className="section-heading">
        <div>
          <h2>Memory</h2>
          <p className="muted">Search semantic and episodic memories, or manage memory proposals.</p>
        </div>
      </div>

      <div className="form-group">
        <label className="field-label" htmlFor="memory-search-input">
          Search memory
        </label>
        <input
          id="memory-search-input"
          aria-label="Search memory"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Query semantic memory..."
        />
      </div>
      <div className="action-cluster" style={{ marginTop: 0, marginBottom: "var(--space-3)" }}>
        <button type="button" className="btn btn-primary" onClick={() => void search()}>
          Search
        </button>
      </div>
      {message && <p className="mono row-reason" style={{ margin: "var(--space-2) 0" }}>{message}</p>}
      {result && (
        <div className="detail-stack">
          <h3>Semantic memories</h3>
          <ul className="list">
            {result.semantic.map((hit) => (
              <li key={hit.ref} className="row">
                <span className="mono">
                  {hit.ref} confidence={hit.confidence}
                </span>
                <button type="button" className="btn btn-danger" onClick={() => void block(hit.ref)}>
                  Block
                </button>
              </li>
            ))}
          </ul>
          <h3>Episodic matches</h3>
          <ul className="list">
            {result.episodic.map((hit, index) => (
              <li key={`${hit.event_id ?? index}`}>{String(hit.reason_code ?? hit.event_type ?? "event")}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="section-heading" style={{ marginTop: "var(--space-4)" }}>
        <div>
          <h3>Memory proposal</h3>
          <p className="muted">Review and commit or reject pending memory proposals.</p>
        </div>
      </div>
      <div className="form-group">
        <label className="field-label" htmlFor="memory-proposal-id">
          Proposal id
        </label>
        <input
          id="memory-proposal-id"
          aria-label="Proposal id"
          className="mono"
          value={proposalId}
          onChange={(event) => setProposalId(event.target.value)}
        />
      </div>
      <div className="form-group">
        <label className="field-label" htmlFor="memory-digest">
          Digest
        </label>
        <input
          id="memory-digest"
          aria-label="Digest"
          className="mono"
          value={digest}
          onChange={(event) => setDigest(event.target.value)}
        />
      </div>
      <div className="form-group">
        <label className="field-label" htmlFor="memory-reject-reason">
          Reject reason
        </label>
        <input
          id="memory-reject-reason"
          aria-label="Reject reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </div>
      <div className="action-cluster">
        <button type="button" className="btn btn-primary" onClick={() => void publish()}>
          Publish memory
        </button>
        <button type="button" className="btn btn-danger" onClick={() => void reject()}>
          Reject memory
        </button>
      </div>
    </section>
  );
}
