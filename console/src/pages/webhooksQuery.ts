/**
 * What the Webhooks module asks `brain.webhook_routes` for and sends it, and how the answers are
 * read. No React.
 *
 * `docs/screens.html` does not draw webhooks, so the module takes the kit's list and SCREEN 14's
 * detail shape (`pages/webhooks/`), and every fact on it is a field the API sent.
 *
 * **Nothing here decides who may change a subscriber.** `manageable` came from
 * `brain.ops.outbox.may_manage` on the server and only decides whether a control is drawn; every
 * write is decided again by the route. **Nothing here holds a secret after it is sent**: the page
 * clears the field the moment a write is confirmed, whatever the answer, and no body the API sends
 * carries one.
 *
 * **Problems are read by field.** A 422 carries every problem at once, each with a field, a code
 * and a sentence, and the form shows each sentence beside its own field. The reading and the
 * matching were written here first and are `api/errors.readFieldProblems` and `api/problems.ts`
 * now, for every form in the console; `Problem` and `problemsFor` are kept under their old names
 * for the query modules that build blank-field problems in the same shape.
 *
 * Task ids: M27.8.12, M27.8.5
 */

import type { FieldProblem } from "../api/problems";
import type { components } from "../api/schema";

export { problemsFor } from "../api/problems";

export type WebhooksBody = components["schemas"]["WebhooksView"];
export type SubscriberRow = components["schemas"]["WebhookSubscriberView"];
export type DeliveryRow = components["schemas"]["DeliveryView"];
export type ChangeRow = components["schemas"]["ChangeView"];
export type DispatcherBody = components["schemas"]["DispatcherView"];
export type InboundChannelRow = components["schemas"]["InboundChannelView"];
export type RegistrationBody = components["schemas"]["RegistrationAsked"];
export type SecretBody = components["schemas"]["SecretAsked"];

/** Where the API keeps the screen, and the three writes beneath it. */
export const WEBHOOKS_API_PATH = "/webhooks";
export const REGISTER_API_PATH = "/webhooks/subscribers";

export function secretApiPath(subscriberId: string): string {
  return `/webhooks/subscribers/${encodeURIComponent(subscriberId)}/secret`;
}

export function switchOffApiPath(subscriberId: string): string {
  return `/webhooks/subscribers/${encodeURIComponent(subscriberId)}/switch-off`;
}

/** The console address and the menu's label. */
export const WEBHOOKS_PATH = "/webhooks";
export const WEBHOOKS_LABEL = "Webhooks";

/** One subscriber's page. The id is the name its registrar gave it, which is how people name it. */
export function webhookAddress(subscriberId: string): string {
  return `${WEBHOOKS_PATH}/${encodeURIComponent(subscriberId)}`;
}

/** A person by name, from the page's `people`, or the sentence for someone the directory does not list. */
export function personWords(people: Readonly<Record<string, string>> | undefined, id: string): string {
  return people?.[id] ?? "someone no longer listed";
}

/** What each state of an arriving channel's check is called on the screen. */
export const VERIFICATION_LABELS: Record<InboundChannelRow["verification"], string> = {
  written: "Written",
  not_written: "Not written",
  not_a_webhook: "Not a webhook",
};

/** How the dispatch's last run ended, in words: finished, failed, or still going. */
export function dispatcherOutcome(dispatcher: DispatcherBody): string {
  if (dispatcher.last_finished_at === null) {
    return "Still running, or stopped without recording an end";
  }
  if (dispatcher.last_outcome === "failed") {
    return `Failed at ${when(dispatcher.last_finished_at)}`;
  }
  return `Finished at ${when(dispatcher.last_finished_at)}`;
}

/** Read `WebhooksView` out of a response body, or null when it is not one. */
export function readWebhooks(payload: unknown): WebhooksBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { subscribers?: unknown; kinds?: unknown; inbound?: unknown };
  if (!Array.isArray(body.subscribers) || !Array.isArray(body.kinds) || !body.inbound) {
    return null;
  }
  return payload as WebhooksBody;
}

/** One problem the API found with what was sent: `api/errors.FieldProblem`, under its first name. */
export type Problem = FieldProblem;

/**
 * What `brain.ops.webhook_admin` tells a person for each field left blank, in its own words.
 *
 * **Only blankness is judged here, before the confirmation opens.** A registration with no id, no
 * address, no kind or no secret was one press from a confirmation asking "Register this subscriber
 * to be told at this address?", which a person could agree to and be refused for afterwards. Every
 * other rule, the id's shape, the address's host and a secret's length, stays the API's alone,
 * because a second copy of those is the copy that drifts from the first. The sentences are copied
 * from the Python and `tests/webhooks-page.test.tsx` holds them to it.
 */
export const BLANK_SENTENCES = Object.freeze({
  subscriber_id: "Give the subscriber an id, such as the name of the system it tells.",
  endpoint: "Give the https address the subscriber receives at.",
  kinds:
    "Choose at least one kind of thing to be told about. A subscriber told about nothing should not be registered.",
  secret: "Paste the signing secret you gave the receiver. It is never shown again.",
});

/** The blank fields of a registration, as the problems the API would have answered with. */
export function blankRegistrationProblems(
  subscriberId: string,
  endpoint: string,
  kinds: readonly string[],
  secret: string,
): Problem[] {
  const found: Problem[] = [];
  // Each test is the Python's own: an id is judged exactly as given, the others with their
  // outer white space removed.
  if (subscriberId === "") {
    found.push({ field: "subscriber_id", code: "blank", message: BLANK_SENTENCES.subscriber_id });
  }
  if (endpoint.trim() === "") {
    found.push({ field: "endpoint", code: "blank", message: BLANK_SENTENCES.endpoint });
  }
  if (kinds.length === 0) {
    found.push({ field: "kinds", code: "none", message: BLANK_SENTENCES.kinds });
  }
  return [...found, ...blankSecretProblems(secret)];
}

/** A replacement secret left blank, as the problem the API would have answered with. */
export function blankSecretProblems(secret: string): Problem[] {
  return secret.trim() === "" ? [{ field: "secret", code: "blank", message: BLANK_SENTENCES.secret }] : [];
}

/** What a person sees in the "When" columns. */
export function when(stamp: string | null | undefined): string {
  if (!stamp) {
    return "";
  }
  const moment = new Date(stamp);
  return Number.isNaN(moment.getTime()) ? stamp : moment.toISOString().replace("T", " ").slice(0, 16);
}

/** The secret, in a word: held, not held, or not known when the vault could not be asked. */
export function secretWord(row: SubscriberRow): string {
  if (row.secret_held === null) {
    return "Not known";
  }
  return row.secret_held ? "Held" : "Not held";
}

/** Where a delivery got to, in words. */
export const DELIVERY_STATE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  pending: "Waiting",
  delivered: "Delivered",
  exhausted: "Given up",
});

/** What each change is called on the screen. */
export const CHANGE_LABELS: Readonly<Record<string, string>> = Object.freeze({
  registered: "Registered",
  secret_replaced: "Secret replaced",
  switched_off: "Switched off",
});

/** What each field of the registration accepts, said under it before anything is sent. */
export const REGISTRATION_FORMATS = Object.freeze({
  subscriber_id: "Up to 63 lower-case letters, digits and underscores, starting with a letter, such as billing_bridge.",
  endpoint: "An https address on the public internet, where the receiver listens.",
  kinds: "Choose at least one. A subscriber is sent identifiers, never content.",
});

/** What a signing secret accepts, with the minimum the API serves. */
export function secretFormat(minimum: number): string {
  return `At least ${String(minimum)} characters, generated rather than typed, and given to the receiver first. It is never shown again.`;
}

/** The body a registration sends: exactly the four fields the route declares. */
export function registrationBody(
  subscriberId: string,
  endpoint: string,
  kinds: readonly string[],
  secret: string,
): RegistrationBody {
  return { subscriber_id: subscriberId, endpoint, kinds: [...kinds], secret };
}

/** The body a rotation sends. */
export function secretBody(secret: string): SecretBody {
  return { secret };
}
