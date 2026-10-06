/**
 * The administrator's one-time code, computed from the secret the job minted for this run.
 *
 * **RFC 6238 over the secret's own bytes.** Keycloak keeps an imported code secret as the
 * characters it was given and hashes their UTF-8 bytes (no base32 step: the credential states no
 * `secretEncoding`), so the key here is the string as typed. The policy is the realm's:
 * `brain.ops.browser_harness.CODE_POLICY`, HmacSHA1, six digits, thirty seconds. A different
 * period or algorithm here is a sign-in that fails every time with "Invalid authenticator code".
 *
 * **A code is used once.** The realm does not accept a code twice (Keycloak's
 * `otpPolicyCodeReusable` is false by default), and the harness signs the administrator in more
 * than once a minute, so `freshCode` waits for the next period rather than replaying one. The
 * last period used is kept in a file rather than in memory, because Playwright starts a new worker
 * process for each project and the `furnish` project's code would otherwise be forgotten.
 * Rejected: turning reuse on in the harness's realm, which would test a realm no install runs.
 *
 * Task ids: M27.10.6
 */

import { createHmac } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const PERIOD_SECONDS = 30;
export const DIGITS = 6;

/** The code for `secret` at `unixSeconds`, as an authenticator app would show it. */
export function codeAt(secret: string, unixSeconds: number, digits: number = DIGITS): string {
  const counter = Math.floor(unixSeconds / PERIOD_SECONDS);
  const message = Buffer.alloc(8);
  message.writeBigUInt64BE(BigInt(counter));
  const digest = createHmac("sha1", Buffer.from(secret, "utf8")).update(message).digest();
  const offset = (digest[digest.length - 1] ?? 0) & 0x0f;
  const binary = digest.readUInt32BE(offset) & 0x7fffffff;
  return String(binary % 10 ** digits).padStart(digits, "0");
}

const LEDGER = join(tmpdir(), "brain-e2e-last-code-period");

function lastPeriod(): number {
  try {
    return Number(readFileSync(LEDGER, "utf8"));
  } catch {
    return -1;
  }
}

/** A code for `secret` from a period no earlier code in this run came from. */
export async function freshCode(secret: string, now: () => number = Date.now): Promise<string> {
  const lastCounter = lastPeriod();
  for (;;) {
    const seconds = Math.floor(now() / 1000);
    const counter = Math.floor(seconds / PERIOD_SECONDS);
    // A code with under two seconds left can expire between being typed and being checked.
    const left = PERIOD_SECONDS - (seconds % PERIOD_SECONDS);
    if (counter > lastCounter && left > 2) {
      writeFileSync(LEDGER, String(counter), "utf8");
      return codeAt(secret, seconds);
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
