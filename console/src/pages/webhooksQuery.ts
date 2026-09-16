/**
 * What the Webhooks screen asks `brain.webhook_routes` for and sends it, and how the answers are
 * read. No React.
 *
 * `docs/screens.html` does not draw webhooks. The owner's standard in `docs/admin-console.md`
 * lists them as a thing an administrator manages, so the screen takes the design's general shape
 * (a crumb, a heading, a lede, cards holding tables, the hint under a card saying what not to
 * assume) and every fact on it is a field the API sent.
 *
 * **Nothing here decides who may change a subscriber.** `manageable` came from
 * `brain.ops.outbox.may_manage` on the server and only decides whether a control is drawn; every
 * write is decided again by the route. **Nothing here holds a secret after it is sent**: the page
 * clears the field the moment a write is confirmed, whatever the answer, and no body the API sends
 * carries one.
 *
 * **Problems are read by field.** A 422 carries every problem at once, each with a field, a code
 * and a sentence, and the form shows each sentence beside its own field. A body that is not that
 * shape is not a set of problems, and the page shows the API's message instead.
 *
 * Task ids: M27.8.12, M27.8.5
 */

import type { components } from "../api/schema";

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

/** One problem the API found with what was sent. */
export interface Problem {
  readonly field: string;
  readonly code: string;
  readonly message: string;
}

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

/** The problems in a 422's body, or null when the body is not a list of them. */
export function readProblems(payload: unknown): Problem[] | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const problems = (payload as { problems?: unknown }).problems;
  if (!Array.isArray(problems)) {
    return null;
  }
  const read: Problem[] = [];
  for (const one of problems) {
    if (typeof one !== "object" || one === null) {
      return null;
    }
    const { field, code, message } = one as Record<string, unknown>;
    if (typeof field !== "string" || typeof code !== "string" || typeof message !== "string") {
      return null;
    }
    read.push({ field, code, message });
  }
  return read;
}

/** The sentences for one field, in the order the API gave them. */
export function problemsFor(problems: readonly Problem[], field: string): string[] {
  return problems.filter((one) => one.field === field).map((one) => one.message);
}

/** What a person sees in the "When" columns. */
export function when(stamp: string | null | undefined): string {
  if (!stamp) {
    return "";
  }
  const moment = new Date(stamp);
  return Number.isNaN(moment.getTime()) ? stamp : moment.toISOString().replace("T", " ").slice(0, 16);
}

/** The secret column, in words: held since, not held, or not known with the vault's reason. */
export function secretSentence(row: SubscriberRow): string {
  if (row.secret_held === null) {
    return "Not known";
  }
  if (!row.secret_held) {
    return "Not held";
  }
  return row.secret_written_at ? `Held, written ${when(row.secret_written_at)}` : "Held";
}

/** The state column. */
export function stateSentence(row: SubscriberRow): string {
  return row.active ? "On" : `Off since ${when(row.deactivated_at)}`;
}

/** What each change is called on the screen. */
export const CHANGE_LABELS: Readonly<Record<string, string>> = Object.freeze({
  registered: "Registered",
  secret_replaced: "Secret replaced",
  switched_off: "Switched off",
});

/** The filter a person narrows the list with. About the page, never about the company. */
export type StateFilter = "all" | "on" | "off";

export const STATE_FILTERS: readonly StateFilter[] = ["all", "on", "off"];

export const STATE_FILTER_LABELS: Readonly<Record<StateFilter, string>> = Object.freeze({
  all: "On and off",
  on: "On",
  off: "Off",
});

/** The rows on this page that match the filter and the search, in the API's order. */
export function narrowed(
  rows: readonly SubscriberRow[],
  state: StateFilter,
  search: string,
): SubscriberRow[] {
  const needle = search.trim().toLowerCase();
  return rows.filter(
    (row) =>
      (state === "all" || (state === "on") === row.active) &&
      (needle === "" ||
        row.subscriber_id.toLowerCase().includes(needle) ||
        row.endpoint.toLowerCase().includes(needle)),
  );
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
