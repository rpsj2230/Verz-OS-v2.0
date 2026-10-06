/**
 * Signing in through the identity provider's own pages, as a person does.
 *
 * **The console has no password form** (`console/src/auth/constants.ts`,
 * `THERE_IS_NO_PASSWORD_FORM`), so the harness types into Keycloak's login page, and the second
 * factor into Keycloak's code page. Both are the realm every install imports. Rejected: a direct
 * grant to fetch a token, which the realm refuses and which would skip the second factor the
 * harness exists to exercise.
 *
 * **The token is read off the wire, never minted.** The console keeps its tokens in memory, so a
 * spec that needs to call the API as the person it signed in (to look up an id, say) takes the
 * access token from the token response the browser itself received.
 *
 * Task ids: M27.10.6
 */

import { expect, type Page, type Response } from "@playwright/test";
import { ADMIN, type Person } from "./people";
import { freshCode } from "./totp";

const TOKEN_PATH = "/protocol/openid-connect/token";

function isTokenResponse(response: Response): boolean {
  return response.url().includes(TOKEN_PATH) && response.request().method() === "POST";
}

/** Answer Keycloak's login page, and its code page when one follows. Returns the access token. */
export async function answerSignIn(page: Page, person: Person, codeSecret?: () => string): Promise<string> {
  const token = page.waitForResponse(isTokenResponse, { timeout: 60_000 });
  await expect(page.locator("#username")).toBeVisible({ timeout: 30_000 });
  await page.locator("#username").fill(person.username);
  await page.locator("#password").fill(person.password());
  await page.locator("#kc-login").click();
  if (codeSecret) {
    await expect(page.locator("#otp")).toBeVisible({ timeout: 30_000 });
    await page.locator("#otp").fill(await freshCode(codeSecret()));
    await page.locator("#kc-login").click();
  }
  const answered = await token;
  expect(answered.status(), "the token endpoint answered").toBe(200);
  const body = (await answered.json()) as { access_token?: unknown };
  if (typeof body.access_token !== "string") {
    throw new Error("the token response carried no access token");
  }
  console.log(`${person.username} signed in: ${describeToken(body.access_token)}`);
  return body.access_token;
}

/**
 * The claims of an access token that say who it is for and how it was earned, and nothing that
 * would let it be used: no signature, no subject, no session. Logged on every sign-in, because a
 * token the API refuses for its audience or its assurance is otherwise a page that quietly signs
 * the person out, and the reason is in these four claims.
 */
export function describeToken(token: string): string {
  const payload = token.split(".")[1] ?? "";
  const claims = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as Record<string, unknown>;
  return JSON.stringify({ aud: claims["aud"], azp: claims["azp"], typ: claims["typ"], amr: claims["amr"], scope: claims["scope"] });
}

/** Open the console as the administrator, through both factors. Returns the access token. */
export async function signInAsAdmin(page: Page, path = "/"): Promise<string> {
  await page.goto(path);
  return answerSignIn(page, ADMIN, ADMIN.codeSecret);
}

/** Open the console as `person`, with a password alone. Returns the access token. */
export async function signInWithPassword(page: Page, person: Person, path = "/"): Promise<string> {
  await page.goto(path);
  return answerSignIn(page, person);
}
