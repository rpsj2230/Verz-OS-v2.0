/**
 * What the Data steward card asks the API for, and what its one write may send. No React.
 *
 * **The data steward is the person every read of the company's data begins with**, named once per
 * install: by the setup wizard since 2026-09-17, and on the People screen for an install set up
 * before then. `brain.identity.data_steward.DATA_ACCESS_BEGINS_WITH_A_NAMED_STEWARD` is the rule and
 * `brain.data_steward_routes` serves it behind `admin:data_steward` over everything.
 *
 * **Nothing here decides who may name one.** A reader without the authority is answered the API's
 * one refusal, and the card draws nothing for it, exactly as it draws nothing while the answer is on
 * its way or when it failed: the People listing above it already says whether the API was reached,
 * and a second notice about the same request would say it twice. See `A_CARD_NOBODY_MAY_USE_IS_NOT_DRAWN`.
 *
 * **Blank boxes are said before anything is sent**, in the wizard's own sentence for them, so the
 * form never asks to confirm naming nobody. Everything else about a name or an address is the API's
 * to judge and its sentences to say.
 *
 * Task ids: M27.9.9
 */

import type { components } from "../api/schema";
import { messageFor } from "../setup/wizard";

/** Who the steward is, or that nobody is, as `brain.data_steward_routes.StewardView` sends it. */
export type StewardView = components["schemas"]["StewardView"];

/** Why the card draws nothing at all for a refusal, a failure or a pending answer. */
export const A_CARD_NOBODY_MAY_USE_IS_NOT_DRAWN =
  "The card is for an administrator deciding who the data steward is. A reader without that " +
  "authority is refused in the API's one sentence, and drawing that sentence on the People screen " +
  "would tell every reader of the listing that a control exists here they may not use. So a " +
  "refusal draws nothing, and so does a failure, which the listing above already says.";

/** Where the API keeps the steward. */
export const STEWARD_API_PATH = "/govern/data-steward";

export const DATA_STEWARD_HEADING = "Data steward";
export const STEWARD_NAME_LABEL = "Full name";
export const STEWARD_ADDRESS_LABEL = "Work email address";
export const NAME_ANOTHER = "Name this person the data steward";
export const NAME_YOURSELF = "Name yourself the data steward as well";
export const KEEP_AS_IT_IS = "Not now";
export const CONFIRM_NAMING = "Name the data steward";
export const YOURSELF_QUESTION = "Make yourself the data steward as well as an administrator?";

/** The question before naming another person. */
export function anotherQuestion(name: string): string {
  return `Name ${name} the data steward?`;
}

/** The body naming another person, with the typed values trimmed of the space around them. */
export function anotherBody(name: string, address: string): Record<string, unknown> {
  return { same_as_administrator: false, full_name: name.trim(), work_address: address.trim() };
}

/** The body naming the reader. It says so, and carries nothing else. */
export const YOURSELF_BODY: Readonly<Record<string, unknown>> = Object.freeze({
  same_as_administrator: true,
});

/** The answer, or null when it is not the document this card draws. */
export function readSteward(payload: unknown): StewardView | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  // A cast at the boundary, where proving the structure buys nothing: every field the card draws is
  // read back through a `typeof` check before it is used.
  const found = payload as Record<string, unknown>;
  if (typeof found["appointed"] !== "boolean" || typeof found["told"] !== "string") {
    return null;
  }
  return payload as StewardView;
}

/** A blank box's sentence, by field, before anything is sent. Empty when both are filled in. */
export function blankProblems(name: string, address: string): Readonly<Record<string, string>> {
  const needed = messageFor("setup.error.steward_needed");
  const found: Record<string, string> = {};
  if (name.trim() === "") {
    found["steward_full_name"] = needed;
  }
  if (address.trim() === "") {
    found["steward_work_address"] = needed;
  }
  return found;
}

/** The API's problems by field, from a 422 body, or null when the body is not that document. */
export function problemsIn(body: unknown): Readonly<Record<string, string>> | null {
  const list = typeof body === "object" && body !== null ? (body as { problems?: unknown }).problems : undefined;
  if (!Array.isArray(list)) {
    return null;
  }
  const found: Record<string, string> = {};
  for (const one of list) {
    if (typeof one !== "object" || one === null) {
      continue;
    }
    const field = (one as Record<string, unknown>)["field"];
    const message = (one as Record<string, unknown>)["message"];
    if (typeof field === "string" && typeof message === "string" && !(field in found)) {
      found[field] = message;
    }
  }
  return found;
}
