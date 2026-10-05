/**
 * Consenting to a source at its vendor: where the console sends the person, and how it hears back.
 * No React.
 *
 * `brain.connector_routes` serves two routes for a source that authorises by OAuth (M11.8.6). `POST
 * /connectors/{connector}/consent` holds a consent for the person and answers the vendor's own page;
 * the console then sends the person there in this tab. The vendor sends them back to
 * `CONSENT_RETURN_PATH`, a page of this console behind the ordinary sign-in, which hands the answer
 * to `GET /connectors/consent/callback` with the person's own session, once.
 *
 * **The person goes in this tab, not in a pop-up.** The console keeps its token in memory, so the
 * navigation ends it, and the return page signs in again through the identity provider's own session
 * on the way back, as any reload does (`auth/session.ts`). Rejected: a pop-up handing the code back
 * to this tab, which the staff list screen needs because its setup code lives only in the wizard
 * tab's memory; nothing here does, and the state is checked against the person on the server.
 *
 * **The answer is handed over once.** The state is single use on the server, so a page that asked
 * twice, as a development build's effects do, would be told the second time that the consent is not
 * theirs; the return page keeps the one request it made in a ref for the life of its mount.
 *
 * **A person connects their own account from My workspace.** A source each person consents to for
 * themselves is never consented to by whoever connected it: `GET /me/accounts` lists the ones the
 * person may connect, and `POST /me/accounts/{connector}/consent` starts it for them, through the same
 * vendor page and the same return page, which sends them back to My workspace.
 *
 * Task ids: M11.8.6
 */

import { request } from "../../api/client";
import type { components } from "../../api/schema";

/** What `POST /connectors/{connector}/consent` answers. */
export type ConsentStarted = components["schemas"]["ConsentStartedView"];
/** What `GET /connectors/consent/callback` answers. */
export type ConsentAnswered = components["schemas"]["ConsentAnsweredView"];
/** What `GET /me/accounts` answers: the sources a person may connect their own account with. */
export type MyAccounts = components["schemas"]["MyAccountsView"];
export type MyAccount = components["schemas"]["MyAccountView"];

/** `brain.connector_routes.MY_ACCOUNTS_PATH`. */
export const MY_ACCOUNTS_API_PATH = "/me/accounts";

/** `brain.connector_routes.MY_CONSENT_PATH` for one source. */
export function myConsentPath(name: string): string {
  return `${MY_ACCOUNTS_API_PATH}/${encodeURIComponent(name)}/consent`;
}

/** The button that sends a person to the vendor for their own account. */
export function connectMyAccountLabel(vendor: string): string {
  return `Connect my ${vendor} account`;
}

/** `brain.connectors.oauth.CONSENT_RETURN_PATH`: where the vendor sends the person back. */
export const CONSENT_RETURN_PATH = "/connector-consent";

/** `brain.connector_routes.CONSENT_CALLBACK_PATH`. */
export const CONSENT_CALLBACK_API_PATH = "/connectors/consent/callback";

/** `brain.connector_routes.CONSENT_PATH` for one source. */
export function consentPath(name: string): string {
  return `/connectors/${encodeURIComponent(name)}/consent`;
}

/** The address the vendor is told to send the person back to: this console's consent page. */
export function returnAddress(origin: string): string {
  return `${origin}${CONSENT_RETURN_PATH}`;
}

/** The button that sends the person to the vendor. */
export function connectWithLabel(vendor: string): string {
  return `Connect with ${vendor}`;
}

/** What the vendor's answer carried back to the return page, read from its address. */
export interface VendorAnswer {
  readonly state: string;
  readonly code: string;
  readonly error: string;
}

export function vendorAnswer(search: string): VendorAnswer {
  const given = new URLSearchParams(search);
  return {
    state: given.get("state") ?? "",
    code: given.get("code") ?? "",
    error: given.get("error") ?? "",
  };
}

/** The callback's address for one answer: the state, and the code or the vendor's refusal. */
export function callbackPath(answer: VendorAnswer): string {
  const query = new URLSearchParams({ state: answer.state });
  if (answer.code) {
    query.set("code", answer.code);
  }
  if (answer.error) {
    query.set("error", answer.error);
  }
  return `${CONSENT_CALLBACK_API_PATH}?${query.toString()}`;
}

/** Hand one answer to the callback. The page calls this once per answer; see the module note. */
export function handOver(answer: VendorAnswer): ReturnType<typeof request<ConsentAnswered>> {
  return request<ConsentAnswered>(callbackPath(answer));
}
