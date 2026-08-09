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
    <section aria-label="memory">
      <h2>Memory</h2>
      <label>
        Search memory
        <input value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
      <button type="button" onClick={() => void search()}>
        Search
      </button>
      {message && <p>{message}</p>}
      {result && (
        <div>
          <h3>Semantic memories</h3>
          <ul>
            {result.semantic.map((hit) => (
              <li key={hit.ref}>
                <span>
                  {hit.ref} confidence={hit.confidence}
                </span>
                <button type="button" onClick={() => void block(hit.ref)}>
                  Block
                </button>
              </li>
            ))}
          </ul>
          <h3>Episodic matches</h3>
          <ul>
            {result.episodic.map((hit, index) => (
              <li key={`${hit.event_id ?? index}`}>{String(hit.reason_code ?? hit.event_type ?? "event")}</li>
            ))}
          </ul>
        </div>
      )}
      <h3>Memory proposal</h3>
      <label>
        Proposal id
        <input value={proposalId} onChange={(event) => setProposalId(event.target.value)} />
      </label>
      <label>
        Digest
        <input value={digest} onChange={(event) => setDigest(event.target.value)} />
      </label>
      <label>
        Reject reason
        <input value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <button type="button" onClick={() => void publish()}>
        Publish memory
      </button>
      <button type="button" onClick={() => void reject()}>
        Reject memory
      </button>
    </section>
  );
}
