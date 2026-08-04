import { build } from "esbuild";

// tsc alone only compiles TS to ESM JS - it never resolves node_modules
// imports into browser-loadable paths, and Electron's sandboxed preload
// loader rejects `import` syntax outright. esbuild replaces the tsc output
// for these two targets only; `main/*` stays tsc's plain ESM output, since
// the main process runs in Node with full ESM support already.

await build({
  entryPoints: ["src/preload/preload.ts"],
  bundle: true,
  platform: "node",
  format: "cjs",
  outfile: "dist/preload/preload.js",
  external: ["electron"],
});

await build({
  entryPoints: ["src/renderer/index.tsx"],
  bundle: true,
  platform: "browser",
  format: "esm",
  outfile: "dist/renderer/index.js",
});
