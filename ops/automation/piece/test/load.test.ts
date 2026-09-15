// The built piece, loaded the way the Activepieces 0.39.5 engine loads one, and held to
// `contract.json`. Needs `npm run build` first; `tests/unit/test_automation_piece_package.py`
// runs both.
//
// **Loaded with `require`, not `import`.** The engine is compiled to CommonJS, so its
// `await import(packageName)` is a `require` when it runs, and a package that only loads as an
// ES module would pass an `import` here and fail in the sandbox. It then takes the one export
// whose constructor is named `Piece` (`extractPieceFromModule` in `@activepieces/shared`), which
// is the rule the first test applies rather than reaching for a named export.

import { afterEach, test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import contract from "../contract.json" with { type: "json" };
import { buildToolCall } from "../lib/call.ts";

const require = createRequire(import.meta.url);
const CREDENTIAL = "bap.nightly_reminder.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const ADDRESS = "http://app:8000";

function json(path: string): any {
  return JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
}

function thePiece(): any {
  const module = require("../dist") as Record<string, unknown>;
  const pieces = Object.values(module).filter(
    (one) => one !== null && one !== undefined && (one as object).constructor.name === "Piece",
  );
  assert.equal(pieces.length, 1, "the engine takes the first Piece export, so there must be one");
  return pieces[0];
}

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

test("the package loads by require and the engine finds exactly one piece in it", () => {
  const piece = thePiece();
  assert.equal(require.resolve("../dist"), require.resolve("../dist/lib/index.js"));
  assert.equal(piece.displayName, "Company Brain");
  assert.deepEqual(Object.keys(piece.triggers()), []);
});

test("the staged package is CommonJS, named as this one, and bundles what it depends on", () => {
  const root = json("../package.json");
  const staged = json("../dist/package.json");
  assert.equal(staged.type, "commonjs");
  assert.equal(staged.name, root.name);
  assert.equal(staged.version, root.version);
  assert.deepEqual(staged.dependencies, root.dependencies);
  assert.deepEqual(staged.bundleDependencies, Object.keys(root.dependencies));
  for (const [name, version] of Object.entries(root.dependencies)) {
    assert.equal(json(`../dist/node_modules/${name}/package.json`).version, version);
  }
});

test("the piece authenticates with an address and an automation credential, and nothing else", () => {
  const auth = thePiece().auth;
  assert.equal(auth.type, "CUSTOM_AUTH");
  assert.equal(auth.required, true);
  assert.deepEqual(Object.keys(auth.props).sort(), ["baseUrl", "credential"]);
  assert.equal(auth.props.baseUrl.type, "SHORT_TEXT");
  assert.equal(auth.props.baseUrl.required, true);
  assert.equal(auth.props.credential.type, "SECRET_TEXT");
  assert.equal(auth.props.credential.required, true);
});

test("the one action is call_tool and its inputs are exactly the fields the contract sends", () => {
  const piece = thePiece();
  assert.deepEqual(Object.keys(piece.actions()), ["call_tool"]);
  const action = piece.getAction("call_tool");
  assert.equal(action.requireAuth, true);
  assert.deepEqual(Object.keys(action.props).sort(), [...contract.body_fields].sort());
  assert.equal(action.props.tool.type, "SHORT_TEXT");
  assert.equal(action.props.tool.required, true);
  assert.equal(action.props.arguments.type, "JSON");
  assert.equal(action.props.arguments.required, false);
});

test("running the action sends exactly what call.ts builds, to the address in the authentication", async () => {
  const sent: { url: string; init: RequestInit }[] = [];
  globalThis.fetch = (async (url: string, init: RequestInit) => {
    sent.push({ url, init });
    return new Response(JSON.stringify({ rows: [] }), { status: 200 });
  }) as typeof fetch;

  const action = thePiece().getAction("call_tool");
  const answered = await action.run({
    auth: { baseUrl: ADDRESS, credential: CREDENTIAL },
    propsValue: { tool: "local.read_price_list", arguments: { limit: 1 } },
  });

  const expected = buildToolCall(contract, ADDRESS, CREDENTIAL, "local.read_price_list", { limit: 1 });
  assert.equal(sent.length, 1);
  assert.equal(sent[0]!.url, expected.url);
  assert.equal(sent[0]!.init.method, expected.method);
  assert.deepEqual(sent[0]!.init.headers, expected.headers);
  assert.equal(sent[0]!.init.body, expected.body);
  assert.deepEqual(answered, { rows: [] });
});

test("a step with no arguments sends an empty bag rather than no field", async () => {
  const bodies: string[] = [];
  globalThis.fetch = (async (_url: string, init: RequestInit) => {
    bodies.push(String(init.body));
    return new Response("{}", { status: 200 });
  }) as typeof fetch;

  await thePiece().getAction("call_tool").run({
    auth: { baseUrl: ADDRESS, credential: CREDENTIAL },
    propsValue: { tool: "t.x" },
  });

  assert.deepEqual(JSON.parse(bodies[0]!), { tool: "t.x", arguments: {} });
});

test("a refused call fails the step with the status and nothing about the tool", async () => {
  globalThis.fetch = (async () => new Response("{}", { status: 404 })) as typeof fetch;

  await assert.rejects(
    thePiece().getAction("call_tool").run({
      auth: { baseUrl: ADDRESS, credential: CREDENTIAL },
      propsValue: { tool: "local.read_price_list", arguments: {} },
    }),
    (error: Error) => error.message === "the tool call was refused (404)",
  );
});
