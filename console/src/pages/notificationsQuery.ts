/**
 * What the Notifications page asks `brain.notification_routes` for and sends it, and how the
 * answers are read. No React.
 *
 * **Nothing here decides who may change a notice or the relay.** The route answers only a caller
 * holding the notification authority over everything, and every write is decided again there.
 * **Nothing here holds the relay's password after it is sent**: the page clears the field the
 * moment a write is confirmed, whatever the answer, and no body the API sends carries it.
 *
 * **Problems are read by field**, by `api/errors.readFieldProblems` and drawn by
 * `ui/FieldProblems.tsx` as on every form rather than by a second copy, and blank fields are said
 * before a confirmation opens in the API's own words, which `tests/notifications-page.test.tsx`
 * holds to the Python.
 *
 * **The refusal-pattern alerts are the reader's own and are read as a list or a sentence.**
 * `readAlerts` turns an absent list into the API's sentence, as `installQuery.readThrottled`
 * does, so no alert kept and nothing able to keep one are drawn differently.
 *
 * Task ids: M27.8.11, M27.8.5, M23.2.2
 */

import type { components } from "../api/schema";
import type { Problem } from "./webhooksQuery";

export type NotificationsBody = components["schemas"]["NotificationsPage"];
export type NoticeRow = components["schemas"]["NoticeView"];
export type EmailBody = components["schemas"]["RelayView"];
/** One refusal-pattern alert addressed to the reader: about whom, the sentence, and when. */
export type AlertRow = components["schemas"]["DenialAlertView"];

/** The reader's alerts, or the API's sentence saying why there is no list. */
export type Alerts = { readonly rows: readonly AlertRow[] } | { readonly unread: string };

/** The alerts half of the page. Null on the payload is no list, whatever its length would be. */
export function readAlerts(page: NotificationsBody): Alerts {
  const rows = page.alerts;
  if (rows === null || rows === undefined) {
    return { unread: page.alerts_unread ?? "" };
  }
  return { rows };
}

/** Where the API keeps the screen, and the five writes beneath it. */
export const NOTIFICATIONS_API_PATH = "/notifications";
export const RELAY_API_PATH = "/notifications/relay";
export const PASSWORD_API_PATH = "/notifications/relay/password";
export const TRIAL_API_PATH = "/notifications/relay/test";
export const REMOVAL_API_PATH = "/notifications/relay/removal";

/** What each relay field accepts, said under it before anything is sent. */
export const RELAY_FORMATS = Object.freeze({
  host: "The relay's host name only, such as smtp.example.com: no scheme, no port.",
  port: "A whole number from 1 to 65535. 587 is usual with STARTTLS, 465 with TLS.",
  sender: "The address mail is sent from, such as console@example.com.",
  username: "The user name the relay expects. Leave it empty for a relay that takes none.",
  password: "Kept in the vault and never shown again.",
  to: "One email address to send the test message to.",
});

/** A person by name, from the page's `people`, or the sentence for someone the directory does not list. */
export function personWords(people: Readonly<Record<string, string>> | undefined, id: string | null): string {
  return id === null ? "" : (people?.[id] ?? "someone no longer listed");
}

export function noticeApiPath(kind: string): string {
  return `/notifications/notices/${encodeURIComponent(kind)}`;
}

/** The console address and the menu's label. */
export const NOTIFICATIONS_PATH = "/notifications";
export const NOTIFICATIONS_LABEL = "Notifications and email";

/** Read `NotificationsPage` out of a response body, or null when it is not one. */
export function readNotifications(payload: unknown): NotificationsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { notices?: unknown; email?: unknown; securities?: unknown };
  if (!Array.isArray(body.notices) || !Array.isArray(body.securities) || typeof body.email !== "object" || body.email === null) {
    return null;
  }
  return payload as NotificationsBody;
}

/**
 * What `brain.ops.mail` tells a person for each field left blank, in its own words. Every other
 * rule, a host's shape, a port's range and an address's form, stays the API's alone.
 */
export const BLANK_SENTENCES = Object.freeze({
  host: "Give the relay's host name.",
  port: "Give a port from 1 to 65535.",
  sender: "Give an email address.",
  password: "Paste the relay's password. It is never shown again.",
  to: "Give an email address.",
});

/**
 * The blank fields of a relay's configuration, and a port that is not a number at all, as the
 * problems the API would have answered with. A port that is a number out of range is the API's.
 */
export function blankRelayProblems(host: string, port: string, sender: string): Problem[] {
  const found: Problem[] = [];
  if (host.trim() === "") {
    found.push({ field: "host", code: "blank", message: BLANK_SENTENCES.host });
  }
  if (portNumber(port) === null) {
    found.push({ field: "port", code: "out_of_range", message: BLANK_SENTENCES.port });
  }
  if (sender.trim() === "") {
    found.push({ field: "sender", code: "blank", message: BLANK_SENTENCES.sender });
  }
  return found;
}

/** A password left blank, as the problem the API would have answered with. */
export function blankPasswordProblems(password: string): Problem[] {
  return password.trim() === "" ? [{ field: "password", code: "blank", message: BLANK_SENTENCES.password }] : [];
}

/** A recipient left blank, as the problem the API would have answered with. */
export function blankTrialProblems(to: string): Problem[] {
  return to.trim() === "" ? [{ field: "to", code: "blank", message: BLANK_SENTENCES.to }] : [];
}

/** The port field as a number, or null when it is not a whole number the API could read. */
export function portNumber(port: string): number | null {
  return /^\d{1,5}$/.test(port.trim()) ? Number(port.trim()) : null;
}

/** The password, in a word: held, not held, or not known when the vault could not be asked. */
export function passwordWord(email: EmailBody): string {
  const held = email.password.held;
  if (held === null) {
    return "Not known";
  }
  return held ? "Held" : "Not held";
}

/** How a notice reaches people today, in two words. */
export function sentSentence(row: NoticeRow): string {
  return row.sent ? "Sent" : "Not sent yet";
}

/** What a person sees in the "When" columns. */
export function when(stamp: string | null | undefined): string {
  if (!stamp) {
    return "";
  }
  const moment = new Date(stamp);
  return Number.isNaN(moment.getTime()) ? stamp : moment.toISOString().replace("T", " ").slice(0, 16);
}

/** What a switch request sends. */
export function switchBody(on: boolean): components["schemas"]["NoticeSwitchAsked"] {
  return { on };
}

/** What a relay save sends: exactly the route's five fields. */
export function relayBody(
  host: string,
  port: number,
  security: string,
  sender: string,
  username: string,
): components["schemas"]["RelayAsked"] {
  return { host, port, security, sender, username };
}

/** What a password save sends. */
export function passwordBody(password: string): components["schemas"]["RelayPasswordAsked"] {
  return { password };
}

/** What a test message request sends. */
export function trialBody(to: string): components["schemas"]["RelayTrialAsked"] {
  return { to };
}
