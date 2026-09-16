/**
 * The staff list screen's reading of a list before setup is sent: what may be asked, and what may
 * be believed when a sign-in window answers. No React.
 *
 * `brain.setup_staff_routes` serves three things behind the wizard's staff list screen: what a
 * company registers at each directory, the directory's own sign-in page, and one read of the
 * list. This module is the browser's half of those and nothing else.
 *
 * **The sign-in happens in a second window, and that is forced by where the setup code lives.**
 * `pages/FirstRun.tsx` keeps the code in the page's memory and nowhere else, and a navigation to
 * Google, Microsoft or Lark would end that memory. So the vendor's page opens in a pop-up, the
 * vendor returns to `RETURN_PATH` in that pop-up, and `pages/StaffListSignedIn.tsx` hands the
 * code back to this tab and closes. FirstRun's own module note rejects a pop-up for the console's
 * sign-in, because that is a second implementation of `auth/session.ts`; this is a different
 * sign-in, to a different system, that has no first implementation to duplicate.
 *
 * **A message from the pop-up is believed only when three things hold.** It came from this
 * console's own origin, it carries this module's kind, and its state is the one this tab
 * generated for this attempt. Anything else is ignored rather than drawn as a failure: a page
 * that reacted to a stranger's message would let any window this tab can be messaged by decide
 * what the screen says. See `A_MESSAGE_IS_BELIEVED_FROM_THIS_ORIGIN_WITH_THIS_STATE`.
 *
 * **The verifier and the client secret stay in this tab until the read is asked for.** The
 * challenge goes to the vendor through the sign-in page, and the code comes back through the
 * pop-up's address, which is in that window's history and the proxy's log. Neither is worth
 * anything without the verifier, which never leaves this tab except in the read itself, and the
 * secret travels only there too. Neither is ever part of the wizard's answers, so neither is in
 * the appointment.
 *
 * Task ids: M42.5.7
 */

import type { components } from "../api/schema";
import { challengeFor, randomToken } from "../auth/pkce";

/** What `GET /setup/staff-source/registration` answers. */
export type Registrations = components["schemas"]["RegistrationsView"];
/** One directory's registration. */
export type Registration = components["schemas"]["RegistrationView"];
/** What `POST /setup/staff-source/sign-in` takes and answers. */
export type SignInAsked = components["schemas"]["DirectorySignInAsked"];
export type SignInAnswer = components["schemas"]["DirectorySignInView"];
/** What `POST /setup/staff-source/trial` takes. It answers the console trial's own `TrialView`. */
export type TrialAsked = components["schemas"]["StaffTrialAsked"];

/** `brain.setup_staff_routes.REGISTRATION_PATH`, `SIGN_IN_PATH` and `TRIAL_PATH`. */
export const REGISTRATION_PATH = "/setup/staff-source/registration";
export const SIGN_IN_PATH = "/setup/staff-source/sign-in";
export const TRIAL_PATH = "/setup/staff-source/trial";

/** `brain.connectors.staff_directories.RETURN_PATH`: where a directory sends the person back. */
export const RETURN_PATH = "/first-run/staff-list";

/** `brain.identity.staff_adapters.SPREADSHEET`, the one source nobody signs in to. */
export const SPREADSHEET = "spreadsheet";

/** The kind a sign-in window's message carries, so a message of any other kind is not this. */
export const SIGNED_IN_KIND = "brain.staff-list.signed-in";

/** Why a message from the sign-in window is checked three ways before it is believed. */
export const A_MESSAGE_IS_BELIEVED_FROM_THIS_ORIGIN_WITH_THIS_STATE =
  "Any window this tab can be messaged by could post a code. Only a message from this console's " +
  "own origin, of this kind, carrying the state this tab made for this attempt, is the vendor's " +
  "answer to this sign-in; anything else is ignored.";

/** The pop-up's name, so a second press reuses the window rather than opening another. */
export const SIGN_IN_WINDOW = "brain-staff-list-sign-in";

/** One attempt's browser half: the state, the verifier kept here, and the challenge sent. */
export interface Attempt {
  readonly state: string;
  readonly verifier: string;
  readonly challenge: string;
}

/** A fresh attempt. The verifier is two random tokens, which is inside PKCE's 43 to 128. */
export async function newAttempt(): Promise<Attempt> {
  const verifier = `${randomToken()}${randomToken()}`;
  return { state: randomToken(), verifier, challenge: await challengeFor(verifier) };
}

/** Where the directory returns the person: this console's own staff list page. */
export function returnAddress(origin: string): string {
  return `${origin}${RETURN_PATH}`;
}

/** What the sign-in window posts back to this tab. */
export interface SignedIn {
  readonly kind: typeof SIGNED_IN_KIND;
  readonly state: string;
  readonly code: string;
  readonly error: string;
}

/**
 * The code a message carries, or null when the message is not this attempt's answer.
 *
 * An `error` from the vendor is returned as a thrown sentence rather than null, because a person
 * who refused consent should be told that rather than left waiting. See the named constant.
 */
export function codeFrom(
  event: { readonly origin: string; readonly data: unknown },
  origin: string,
  attempt: Attempt,
): string | null {
  if (event.origin !== origin) {
    return null;
  }
  const data = typeof event.data === "object" && event.data !== null ? (event.data as Record<string, unknown>) : {};
  if (data["kind"] !== SIGNED_IN_KIND || data["state"] !== attempt.state) {
    return null;
  }
  const error = typeof data["error"] === "string" ? data["error"] : "";
  if (error !== "") {
    throw new Error(`The directory did not sign you in: ${error}.`);
  }
  const code = typeof data["code"] === "string" ? data["code"] : "";
  return code === "" ? null : code;
}

/** The sign-in request: the code, the source, where it is, and this attempt's public half. */
export function signInBody(
  setupCode: string,
  source: string,
  location: string,
  clientId: string,
  origin: string,
  attempt: Attempt,
): SignInAsked {
  return {
    setup_code: setupCode,
    staff_source: source,
    location,
    client_id: clientId,
    redirect_uri: returnAddress(origin),
    state: attempt.state,
    challenge: attempt.challenge,
  };
}

/** The read of a directory signed in to. The verifier and the secret leave this tab only here. */
export function directoryTrialBody(
  setupCode: string,
  source: string,
  location: string,
  clientId: string,
  clientSecret: string,
  code: string,
  origin: string,
  attempt: Attempt,
): TrialAsked {
  return {
    setup_code: setupCode,
    staff_source: source,
    location,
    sheet: "",
    client_id: clientId,
    client_secret: clientSecret,
    code,
    verifier: attempt.verifier,
    redirect_uri: returnAddress(origin),
  };
}

/** The read of a spreadsheet: its text, as the file the person chose holds it. */
export function sheetTrialBody(setupCode: string, sheet: string): TrialAsked {
  return {
    setup_code: setupCode,
    staff_source: SPREADSHEET,
    location: "",
    sheet,
    client_id: "",
    client_secret: "",
    code: "",
    verifier: "",
    redirect_uri: "",
  };
}
