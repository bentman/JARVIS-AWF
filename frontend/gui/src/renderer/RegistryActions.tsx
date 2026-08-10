import React, { useState } from "react";

export interface RegistryActionsProps {
  onRegistryValidate: (path: string, kind?: string) => Promise<unknown>;
  onRegistryPublish: (path: string, kind: string) => Promise<unknown>;
  onRegistryReindex: () => Promise<unknown>;
  onRegistryRetire: (kind: string, name: string, version: string) => Promise<unknown>;
  onRegistryTrust: (kind: string, name: string, version: string, status: string) => Promise<unknown>;
}

function asText(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function RegistryActions({
  onRegistryValidate,
  onRegistryPublish,
  onRegistryReindex,
  onRegistryRetire,
  onRegistryTrust,
}: RegistryActionsProps): React.JSX.Element {
  const [path, setPath] = useState("");
  const [kind, setKind] = useState("workflows");
  const [name, setName] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [trustStatus, setTrustStatus] = useState("trusted");
  const [result, setResult] = useState<string>("");
  const [error, setError] = useState<string>("");

  const runAction = async (action: () => Promise<unknown>) => {
    setError("");
    setResult("");
    try {
      setResult(asText(await action()));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  return (
    <section aria-label="Registry actions">
      <h2>Registry actions</h2>
      <p>Validate, publish, reindex, retire, or set trust through the AWF core registry operations.</p>
      <label>
        Draft path
        <input
          aria-label="Registry draft path"
          value={path}
          onChange={(event) => setPath(event.currentTarget.value)}
          placeholder="data/proposals/example.yaml"
        />
      </label>
      <label>
        Kind
        <input aria-label="Registry kind" value={kind} onChange={(event) => setKind(event.currentTarget.value)} />
      </label>
      <label>
        Name
        <input aria-label="Registry name" value={name} onChange={(event) => setName(event.currentTarget.value)} />
      </label>
      <label>
        Version
        <input
          aria-label="Registry version"
          value={version}
          onChange={(event) => setVersion(event.currentTarget.value)}
        />
      </label>
      <label>
        Trust status
        <input
          aria-label="Registry trust status"
          value={trustStatus}
          onChange={(event) => setTrustStatus(event.currentTarget.value)}
        />
      </label>
      <div>
        <button type="button" onClick={() => void runAction(() => onRegistryValidate(path, kind || undefined))}>
          Validate
        </button>
        <button type="button" onClick={() => void runAction(() => onRegistryPublish(path, kind))}>
          Publish
        </button>
        <button type="button" onClick={() => void runAction(() => onRegistryReindex())}>
          Reindex
        </button>
        <button type="button" onClick={() => void runAction(() => onRegistryRetire(kind, name, version))}>
          Retire
        </button>
        <button type="button" onClick={() => void runAction(() => onRegistryTrust(kind, name, version, trustStatus))}>
          Set trust
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {result && <pre aria-label="Registry action result">{result}</pre>}
    </section>
  );
}
