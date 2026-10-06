/**
 * The code the harness types is the code an authenticator app shows.
 *
 * Deleting this leaves a wrong code computation looking like Keycloak refusing the administrator,
 * which is the slowest possible place to find it: a whole stack started to learn a hash was wrong.
 */

import { expect, test } from "@playwright/test";
import { codeAt } from "../lib/totp";

// RFC 6238 appendix B, SHA-1, with the RFC's own twenty-byte ASCII key.
const RFC_KEY = "12345678901234567890";
const VECTORS: ReadonlyArray<readonly [number, string]> = [
  [59, "94287082"],
  [1111111109, "07081804"],
  [1111111111, "14050471"],
  [1234567890, "89005924"],
  [2000000000, "69279037"],
  [20000000000, "65353130"],
];

test("the one-time code matches every RFC 6238 SHA-1 vector", () => {
  for (const [seconds, expected] of VECTORS) {
    expect(codeAt(RFC_KEY, seconds, 8)).toBe(expected);
  }
});

test("a six-digit code is the last six digits of the eight-digit one", () => {
  for (const [seconds, expected] of VECTORS) {
    expect(codeAt(RFC_KEY, seconds)).toBe(expected.slice(-6));
  }
});
