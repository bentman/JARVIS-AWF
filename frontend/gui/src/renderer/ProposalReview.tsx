import React, { useState } from "react";
import { stateClass } from "./state.js";

export interface ProposalSummary {
  proposal_id: string;
  name: string;
  version: string;
  status: "draft" | "published" | "rejected";
  draft_digest: string;
  draft_path: string;
  summary: string;
  content: string;
}

export interface ProposalReviewProps {
  onProposalGet: (proposalId: string) => Promise<ProposalSummary>;
  onProposalPublish: (proposalId: string, digest: string) => Promise<unknown>;
  onProposalReject: (proposalId: string, reason?: string) => Promise<unknown>;
}

export function ProposalReview({
  onProposalGet,
  onProposalPublish,
  onProposalReject,
}: ProposalReviewProps): React.JSX.Element {
  const [proposalId, setProposalId] = useState("");
  const [proposal, setProposal] = useState<ProposalSummary | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    if (!proposalId.trim()) return;
    setBusy(true);
    try {
      setProposal(await onProposalGet(proposalId.trim()));
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    if (!proposal) return;
    setBusy(true);
    try {
      await onProposalPublish(proposal.proposal_id, proposal.draft_digest);
      setProposal(await onProposalGet(proposal.proposal_id));
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!proposal) return;
    setBusy(true);
    try {
      await onProposalReject(proposal.proposal_id, reason || undefined);
      setProposal(await onProposalGet(proposal.proposal_id));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="Workflow proposal review" className="card">
      <div className="section-heading">
        <div>
          <h2>Workflow proposal review</h2>
          <p className="muted">Inspect, publish, or reject generated workflow proposals.</p>
        </div>
        {proposal && <span className={`chip ${stateClass(proposal.status)}`}>{proposal.status}</span>}
      </div>

      <div className="form-group">
        <label className="field-label" htmlFor="proposal-id-input">
          Proposal id
        </label>
        <input
          id="proposal-id-input"
          aria-label="Proposal id"
          className="mono"
          value={proposalId}
          onChange={(event) => setProposalId(event.currentTarget.value)}
          placeholder="e.g. p-1234"
        />
      </div>

      <div className="action-cluster" style={{ marginTop: 0, marginBottom: "var(--space-4)" }}>
        <button className="btn btn-primary" onClick={() => void load()} disabled={busy || !proposalId.trim()}>
          Load proposal
        </button>
      </div>

      {proposal && (
        <article className="detail-stack">
          <div className="section-heading" style={{ marginTop: "var(--space-3)" }}>
            <div>
              <h3>
                {proposal.name}@{proposal.version}
              </h3>
              <p className="mono row-reason">Path: {proposal.draft_path}</p>
            </div>
            <span className={`chip ${stateClass(proposal.status)}`}>{proposal.status}</span>
          </div>
          <p className="mono row-reason" style={{ marginTop: "var(--space-1)" }}>
            Digest: {proposal.draft_digest}
          </p>
          <p style={{ margin: "var(--space-2) 0" }}>{proposal.summary}</p>
          <pre className="pre-scroll">{proposal.content}</pre>

          <div className="action-cluster" style={{ marginBottom: "var(--space-4)" }}>
            <button className="btn btn-primary" onClick={() => void publish()} disabled={busy || proposal.status !== "draft"}>
              Publish
            </button>
          </div>

          <div className="form-group" style={{ maxWidth: "440px" }}>
            <label className="field-label" htmlFor="reject-reason-input">
              Reject reason
            </label>
            <input
              id="reject-reason-input"
              aria-label="Reject reason"
              value={reason}
              onChange={(event) => setReason(event.currentTarget.value)}
              placeholder="Reason for rejection"
            />
          </div>

          <div className="action-cluster" style={{ marginTop: 0 }}>
            <button className="btn btn-danger" onClick={() => void reject()} disabled={busy || proposal.status !== "draft"}>
              Reject
            </button>
          </div>
        </article>
      )}
    </section>
  );
}
