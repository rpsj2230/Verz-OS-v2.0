// The request a step sends, held to `contract.json`. Runs on Node's own test runner with its
// own type stripping, so no dependency is installed to run it.

import { test } from "node:test";
import assert from "node:assert/strict";
import contract from "../contract.json" with { type: "json" };
import { buildToolCall } from "../lib/call.ts";

const CREDENTIAL = "bap.nightly_reminder.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

test("a step sends a tool name and an argument bag and nothing else", () => {
  const built = buildToolCall(contract, "http://app:8000", CREDENTIAL, "local.read_price_list", {
    limit: 1,
  });
  const body = JSON.parse(built.body);
  assert.deepEqual(Object.keys(body).sort(), [...contract.body_fields].sort());
  assert.equal(body.tool, "local.read_price_list");
  assert.deepEqual(body.arguments, { limit: 1 });
});

test("the call goes to the contracted path with the credential as a bearer", () => {
  const built = buildToolCall(contract, "http://app:8000", CREDENTIAL, "t.x", {});
  assert.equal(built.url, `http://app:8000${contract.path}`);
  assert.equal(built.method, contract.method);
  assert.equal(built.headers[contract.credential_header], `${contract.credential_scheme} ${CREDENTIAL}`);
});

test("a trailing slash on the address does not change the path", () => {
  const built = buildToolCall(contract, "http://app:8000///", CREDENTIAL, "t.x", {});
  assert.equal(built.url, `http://app:8000${contract.path}`);
});

test("a credential that is not an automation credential is refused before anything is built", () => {
  assert.throws(() => buildToolCall(contract, "http://app:8000", "eyJhbGciOi.person.token", "t.x", {}));
});
