// Builds the package Activepieces installs, into `dist/`, from nothing but this directory.
//
// Three steps, and each is here because the obvious shortcut is wrong.
//
// **`dist/` is removed first.** `tsc` never deletes output, so a renamed module would stay in
// the package beside its replacement and the engine would load whichever export it met first.
//
// **CommonJS, with a `package.json` of its own inside `dist/`.** The Activepieces 0.39.5 engine
// is compiled with `module: commonjs`, so its `await import(packageName)` is a `require` at
// run time, and a package that is ES modules fails there on Node 18 with nothing in the flow to
// say why. This directory stays `"type": "module"` so the tests keep running on Node's own type
// stripping; the staged file is what makes `dist/` CommonJS without changing that.
//
// **The runtime dependencies are bundled into the tarball, copied from `package-lock.json`.**
// The canvas reaches the internet only through the egress proxy, and the npm registry is not on
// `brain.ops.automation.EGRESS_ALLOWLIST`, so a piece whose install has to fetch its framework
// is a piece that cannot be installed there. Read from the lock rather than from a walk of
// `node_modules`, so what ships is what was pinned and not whatever a laptop happens to hold.

import { execFileSync } from "node:child_process";
import { cpSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";

const here = new URL("../", import.meta.url);
const dist = new URL("dist/", here);
const require = createRequire(import.meta.url);

rmSync(dist, { recursive: true, force: true });

execFileSync(process.execPath, [require.resolve("typescript/bin/tsc"), "-p", "tsconfig.json"], {
  cwd: here,
  stdio: "inherit",
});

const root = JSON.parse(readFileSync(new URL("package.json", here), "utf8"));
const lock = JSON.parse(readFileSync(new URL("package-lock.json", here), "utf8"));

const staged = {
  name: root.name,
  version: root.version,
  description: root.description,
  type: "commonjs",
  main: "lib/index.js",
  dependencies: root.dependencies,
  bundleDependencies: Object.keys(root.dependencies),
};
writeFileSync(new URL("package.json", dist), `${JSON.stringify(staged, null, 2)}\n`);

for (const [path, entry] of Object.entries(lock.packages)) {
  if (path === "" || entry.dev === true) {
    continue;
  }
  cpSync(new URL(`${path}/`, here), new URL(`${path}/`, dist), { recursive: true });
}
