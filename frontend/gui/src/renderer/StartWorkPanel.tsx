import React from "react";
import type { OperatorInputField, OperatorStartOption } from "./Dashboard.js";
import { stateClass } from "./state.js";

export interface StartWorkPanelProps {
  options: OperatorStartOption[];
  workflowOptions?: string[];
  selectedWorkflowRef?: string;
  onWorkflowRefChange?: (workflowRef: string) => void;
  onStart?: (workflowRef: string, input: Record<string, unknown>) => Promise<{ run_id?: string; status?: string }>;
  onRunStarted?: (runId: string) => void;
}

function defaultInput(option: OperatorStartOption | undefined): Record<string, unknown> {
  const input: Record<string, unknown> = {};
  for (const field of option?.input_schema_summary?.fields ?? []) {
    if (field.default !== undefined && field.default !== null) {
      input[field.name] = field.default;
    } else if (field.type === "boolean") {
      input[field.name] = false;
    } else if (field.enum && field.enum.length > 0) {
      input[field.name] = field.enum[0];
    } else if (field.required) {
      input[field.name] = "";
    }
  }
  return input;
}

function coerceFieldValue(field: OperatorInputField, value: string | boolean): unknown {
  if (field.type === "boolean") return Boolean(value);
  if (field.type === "integer") return Number.parseInt(String(value), 10);
  if (field.type === "number") return Number.parseFloat(String(value));
  return value;
}

function parseRawInput(rawInput: string): Record<string, unknown> {
  if (!rawInput.trim()) return {};
  const parsed = JSON.parse(rawInput) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Advanced input must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

export function StartWorkPanel({
  options,
  workflowOptions = [],
  selectedWorkflowRef,
  onWorkflowRefChange,
  onStart,
  onRunStarted,
}: StartWorkPanelProps): React.JSX.Element {
  const refs = React.useMemo(
    () => Array.from(new Set([...options.map((option) => option.workflow_ref), ...workflowOptions])).sort(),
    [options, workflowOptions],
  );
  const firstRef = selectedWorkflowRef || refs[0] || "assistant-default@1.0.0";
  const [workflowRef, setWorkflowRef] = React.useState(firstRef);
  const selected = options.find((option) => option.workflow_ref === workflowRef);
  const [input, setInput] = React.useState<Record<string, unknown>>(() => defaultInput(selected));
  const [rawInput, setRawInput] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    setWorkflowRef(firstRef);
  }, [firstRef]);

  React.useEffect(() => {
    setInput(defaultInput(selected));
    setRawInput("");
    setError(null);
  }, [selected?.workflow_ref]);

  const setSelectedRef = (nextRef: string) => {
    setWorkflowRef(nextRef);
    onWorkflowRefChange?.(nextRef);
  };

  const start = async () => {
    if (!onStart) return;
    setError(null);
    setResult(null);
    setSubmitting(true);
    try {
      const advanced = parseRawInput(rawInput);
      const result = await onStart(workflowRef, { ...input, ...advanced });
      setResult(`Started ${workflowRef}${result.run_id ? ` as ${result.run_id}` : ""}.`);
      if (result.run_id) onRunStarted?.(result.run_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section aria-label="Start work" className="operate-band start-work-panel">
      <div className="section-heading">
        <div>
          <h2>Start work</h2>
          <p className="muted">Choose a workflow, provide its inputs, then watch the run from this view.</p>
        </div>
        {selected && <span className={`chip ${stateClass(selected.status)}`}>{selected.status}</span>}
      </div>
      <label>
        Workflow
        <select aria-label="Workflow" value={workflowRef} onChange={(event) => setSelectedRef(event.currentTarget.value)}>
          {refs.map((ref) => (
            <option key={ref} value={ref}>
              {ref}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <div className="workflow-summary">
          <span className={`chip ${stateClass(selected.source ?? "config")}`}>{selected.source ?? "config"}</span>
          {selected.trust_status && <span className={`chip ${stateClass(selected.trust_status)}`}>{selected.trust_status}</span>}
          {selected.digest && <span className="mono row-reason">{selected.digest.slice(0, 24)}</span>}
        </div>
      )}
      {(selected?.input_schema_summary?.fields ?? []).map((field) => (
        <label key={field.name}>
          {field.name}
          {field.enum && field.enum.length > 0 ? (
            <select
              aria-label={field.name}
              value={String(input[field.name] ?? "")}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setInput((prev) => ({ ...prev, [field.name]: coerceFieldValue(field, value) }));
              }}
            >
              {field.enum.map((value) => (
                <option key={String(value)} value={String(value)}>
                  {String(value)}
                </option>
              ))}
            </select>
          ) : field.type === "boolean" ? (
            <input
              aria-label={field.name}
              type="checkbox"
              checked={Boolean(input[field.name])}
              onChange={(event) => setInput((prev) => ({ ...prev, [field.name]: event.currentTarget.checked }))}
            />
          ) : (
            <input
              aria-label={field.name}
              className={field.name === "objective" ? "" : "mono"}
              required={field.required}
              type={field.type === "integer" || field.type === "number" ? "number" : "text"}
              value={String(input[field.name] ?? "")}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setInput((prev) => ({ ...prev, [field.name]: coerceFieldValue(field, value) }));
              }}
            />
          )}
        </label>
      ))}
      <details>
        <summary>Advanced input</summary>
        <textarea
          aria-label="Advanced input"
          className="mono"
          value={rawInput}
          onChange={(event) => setRawInput(event.currentTarget.value)}
          placeholder='{"objective":"check the system"}'
        />
      </details>
      <div className="inline-actions">
        <button type="button" className="btn btn-primary" disabled={!onStart || submitting} onClick={() => void start()}>
          {submitting ? "Starting..." : "Start workflow"}
        </button>
        {selected?.primary_action?.command && <code>{selected.primary_action.command}</code>}
      </div>
      {error && <p role="alert">{error}</p>}
      {result && <p role="status">{result}</p>}
    </section>
  );
}
