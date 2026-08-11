# ADR-0014: adopt the Node.js 24 LTS frontend policy

## Status

Implemented.

## Context

The frontend workspace previously used a Node.js 26+ current-release policy
while replacing the vulnerable Vitest 2/Vite 5 chain. JARVIS-AWF also supports
Cline CLI as an implementation adapter, and Cline's npm CLI supports Node.js
`>=22`. Operators on Windows ARM64 commonly install the OpenJS Node.js LTS
package, and Linux/WSL operators commonly use nvm or NodeSource LTS channels.
Node.js 24 is the current LTS line across those host classes.

## Decision

The frontend workspace supports Node.js `>=24.15.0`, enforced by npm
`engine-strict`. The floor follows the current Node.js 24 LTS line while
respecting the concrete dependency floor in the committed frontend lockfile.
Newer Node.js majors remain accepted unless compatibility evidence requires a
documented revision.

All direct frontend dependencies use the stable release available at this
decision that supports the Node.js 24 LTS floor: TypeScript `^7.0.2`, Vitest
`^4.1.10`, esbuild `^0.28.1`, jsdom `^30.0.1`, Electron, React, Ink,
testing-library, and Node.js 24 type packages. Manifest ranges remain caret
ranges; the committed npm lockfile records the tested concrete resolution.
Transitive Vite and nanoid remain indirect dependencies.

The workspace declares npm 11's install-script approval in its root
`package.json`, rather than relying on an operator-local `.npmrc`. The sole
approval is `esbuild@0.28.1`, whose `postinstall` runs `node install.js` to
provide esbuild's platform-specific binary. npm ignores an `allow-scripts`
setting from `.npmrc` when the package manifest declares `allowScripts`; this
keeps the required approval reviewable and reproducible for every checkout.

The root `dev` command builds every frontend workspace and then starts the
existing `awf-gui` Electron application. GUI launch remains an
operator-visible smoke check.

## Consequences

Node.js versions earlier than `24.15.0` are intentionally rejected for
frontend installation and development. The AWF specification and QuickStarts
state the same Node.js 24 LTS requirement. Future direct frontend-dependency
refreshes should preserve the active LTS floor unless there is host-class
evidence for changing it, and validate the complete frontend workspace before
updating the lockfile. A refresh that changes esbuild's resolved version must
also review its install script and update the exact `allowScripts` entry; no
other install scripts are implicitly approved. Use
`npm --prefix frontend install-scripts ls` to review the current decision.
