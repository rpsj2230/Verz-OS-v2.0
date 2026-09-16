/**
 * What the Notifications screen asks `brain.notification_routes` for and sends it, and how the
 * answers are read. No React.
 *
 * **Nothing here decides who may change a notice or the relay.** The route answers only a caller
 * holding the notification authority over everything, and every write is decided again there.
 * **Nothing here holds the relay's password after it is sent**: the page clears the field the
 * moment a write is confirmed, whatever the answer, and no body the API sends carries it.
 *
 * **Problems are read by field**, with `readProblems` and `problemsFor` from the Webhooks screen's
 * module rather than a second copy, and blank fields are said before a confirmation opens in the
 * API's own words, which `tests/notifications-page.test.tsx` holds to the Python.
 *
 * Task ids: M27.8.11, M27.8.5
 */

import type { components } from "../api/schema";
import type { Problem } from "./webhooksQuery";

export type NotificationsBody = components["schemas"]["NotificationsPage"];
export type NoticeRow = components["schemas"]["NoticeView"];
export type EmailBody = components["schemas"]["RelayView"];

/** Where the API keeps the screen, and the four writes beneath it. */
export const NOTIFICATIONS_API_PATH = "/notifications";
export const RELAY_API_PATH = "/notifications/relay";
export const PASSWORD_API_PATH = "/notifications/relay/password";
export const TRIAL_API_PATH = "/notifications/relay/test";

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

/** The password line, in words: held since, not held, or not known with the vault's reason. */
export function passwordSentence(email: EmailBody): string {
  const password = email.password;
  if (password.held === null) {
    return "Not known";
  }
  if (!password.held) {
    return "Not held";
  }
  return password.written_at === null ? "Held" : `Held, written ${when(password.written_at)}`;
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
