# ADR-0014: adopt the Node.js 26+ current frontend policy

## Status

Implemented.

## Context

The frontend workspace previously used a temporary Node.js 24-only support
window while replacing the vulnerable Vitest 2/Vite 5 chain. JARVIS-AWF is a
personal development project that keeps its development toolchains current;
the Windows counterparts already use Node.js 26.

## Decision

The frontend workspace supports Node.js `>=26`, enforced by npm
`engine-strict`. The floor intentionally has no upper bound: newer Node.js
majors remain accepted unless compatibility evidence requires a documented
revision.

All direct frontend dependencies use the current stable release available at
this decision: TypeScript `^7.0.2`, Vitest `^4.1.10`, esbuild `^0.28.1`,
jsdom `^30.0.1`, and matching current Electron, React, Ink, testing-library,
and type packages. Manifest ranges remain caret ranges; the committed npm
lockfile records the tested concrete resolution. Transitive Vite and nanoid
remain indirect dependencies.

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

Node.js 24 and older hosts are intentionally rejected for frontend
installation and development. The AWF specification and QuickStarts state the
same Node.js 26+ requirement. Future direct frontend-dependency refreshes
should select then-current stable releases and validate the complete frontend
workspace before updating the lockfile. A refresh that changes esbuild's
resolved version must also review its install script and update the exact
`allowScripts` entry; no other install scripts are implicitly approved. Use
`npm --prefix frontend install-scripts ls` to review the current decision.
