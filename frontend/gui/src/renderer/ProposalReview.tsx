import React, { useState } from "react";

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
    <section aria-label="Workflow proposal review">
      <h2>Workflow proposal review</h2>
      <label>
        Proposal id
        <input value={proposalId} onChange={(event) => setProposalId(event.currentTarget.value)} />
      </label>
      <button onClick={() => void load()} disabled={busy || !proposalId.trim()}>
        Load proposal
      </button>
      {proposal && (
        <article>
          <h3>
            {proposal.name}@{proposal.version}
          </h3>
          <p>Status: {proposal.status}</p>
          <p>Digest: {proposal.draft_digest}</p>
          <p>Path: {proposal.draft_path}</p>
          <p>{proposal.summary}</p>
          <pre>{proposal.content}</pre>
          <button onClick={() => void publish()} disabled={busy || proposal.status !== "draft"}>
            Publish
          </button>
          <label>
            Reject reason
            <input value={reason} onChange={(event) => setReason(event.currentTarget.value)} />
          </label>
          <button onClick={() => void reject()} disabled={busy || proposal.status !== "draft"}>
            Reject
          </button>
        </article>
      )}
    </section>
  );
}
