/**
 * What the Channels module and a person's own channels card ask the API for, and what they may
 * send. No React.
 *
 * **Two sides of one fact, on two screens.** An administrator sees each channel's record, its
 * switch, what its adapter declares it can carry, how it is doing and who is bound on it; a person
 * sees, in My workspace, which chats they may connect and which they have, and asks for the code
 * that connects one. `brain.channel_routes` serves the record's writes, the test message and the
 * deliveries; `brain.binding_routes` serves the module list, one channel's row, its health and
 * binding; `brain.console.channel_health` decides what the deliveries say; `brain.channels.binding`
 * decides everything about a code.
 *
 * **Nothing here decides who may see or change a channel.** The API answers a reader without the
 * channel's authority, a channel that is not switched on and a name that is no channel with one
 * absence, and the pages draw whatever they were sent.
 *
 * **The secret is never read and never shown.** A channel says whether its secret is held, or that
 * the vault could not be asked, and the set-up form sends a new secret once and empties the field
 * whatever came back, for `signInLinksQuery.AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT`'s reason.
 *
 * **A code is shown once, where it was asked for.** The API answers it with `no-store` and keeps
 * only its digest; the card holds it in memory until the page is left and says how long it lasts.
 *
 * Task ids: M10.3.1, M10.3.4, M10.1.2, M10.1.3, M10.1.4, M27.13.1
 */

import type { FieldProblem } from "../api/errors";
import type { components } from "../api/schema";
import type { FilterChoice, SortChoice } from "../components/listing";

export type HealthBody = components["schemas"]["ChannelHealthView"];
export type BindingsBody = components["schemas"]["ChannelBindingsView"];
export type BoundRow = components["schemas"]["BoundPersonView"];
export type UnboundBody = components["schemas"]["ChannelUnboundView"];
export type DeliveriesBody = components["schemas"]["DeliveriesView"];
export type DeliveryRow = components["schemas"]["DeliveryRowView"];
export type TestBody = components["schemas"]["TestView"];
export type MyChannelsBody = components["schemas"]["MyChannelsView"];
export type MyChannelRow = components["schemas"]["MyChannelView"];
export type CodeBody = components["schemas"]["BindingCodeView"];

/** The menu group these pages sit in, the first step of their trails. */
export const GROUP_LABEL = "Channels and notifications";

/** Where the API keeps the asker's own chat channels. */
export const MY_CHANNELS_API_PATH = "/me/channels";

function named(name: string): string {
  return `/channels/${encodeURIComponent(name)}`;
}

export function channelApiPath(name: string): string {
  return named(name);
}
export function switchApiPath(name: string): string {
  return `${named(name)}/switch`;
}
export function testApiPath(name: string): string {
  return `${named(name)}/test`;
}
export function deliveriesApiPath(name: string): string {
  return `${named(name)}/deliveries`;
}
export function healthApiPath(name: string): string {
  return `${named(name)}/health`;
}
export function bindingsApiPath(name: string): string {
  return `${named(name)}/bindings`;
}
export function unbindApiPath(name: string): string {
  return `${named(name)}/bindings/unbind`;
}
export function myCodeApiPath(name: string): string {
  return `/me/channels/${encodeURIComponent(name)}/code`;
}
export function myUnbindApiPath(name: string): string {
  return `/me/channels/${encodeURIComponent(name)}/unbind`;
}

/** A channel's health, in the pill's words. */
export const HEALTH_WORDS: Readonly<Record<string, string>> = {
  not_set_up: "Not set up",
  switched_off: "Switched off",
  quiet: "Nothing yet",
  working: "Working",
  failing: "Failing",
};

export function healthWord(health: string): string {
  return HEALTH_WORDS[health] ?? health;
}

/** A delivery's direction, in words. */
export const DIRECTION_WORDS: Readonly<Record<string, string>> = { inbound: "Received", outbound: "Sent" };

/** A delivery's outcome, in words. */
export const OUTCOME_WORDS: Readonly<Record<string, string>> = {
  accepted: "Accepted",
  redelivered: "Sent again by the vendor",
  sent: "Delivered",
  refused: "Refused",
  unknown: "Not known",
};

/** A refusal's reason as a phrase: "vendor refused". */
export function reasonWords(reason: string | null): string {
  return reason === null ? "" : reason.replaceAll("_", " ");
}

/** A delivery's outcome and reason, as one phrase: "Refused: vendor refused (502)". */
export function deliveryWords(row: DeliveryRow): string {
  const reason = row.reason === null ? "" : `: ${reasonWords(row.reason)}`;
  const status = row.vendor_status === null ? "" : ` (${String(row.vendor_status)})`;
  return `${OUTCOME_WORDS[row.outcome] ?? row.outcome}${reason}${status}`;
}

/** What each tenant field is, and what it accepts: one unbroken line (`channel_routes.tenant_problems`). */
export const TENANT_FORMAT = "One line of at most 500 characters, with no spaces.";

/** Every tenant field left blank, as the problem the form says beside it. */
export function setupProblems(fields: readonly string[], values: Readonly<Record<string, string>>): FieldProblem[] {
  return fields
    .filter((field) => (values[field] ?? "").trim() === "")
    .map((field) => ({ field, code: "blank", message: `Fill in ${field}, which this channel needs before it can reply.` }));
}

/** A blank destination, as the problem the test form says beside it. */
export function testProblems(to: string): FieldProblem[] {
  return to.trim() === "" ? [{ field: "to", code: "blank", message: "Say where the test message goes, in the vendor's terms." }] : [];
}

/**
 * Every part of a secret left empty while another was typed. A secret of parts is saved whole,
 * every part at once or none to keep the ones held, which is
 * `brain.channels.adapter.SEVERAL_PARTS_ARE_WRITTEN_AS_ONE` said beside the fields.
 */
export function partProblems(parts: readonly string[], typed: Readonly<Record<string, string>>): FieldProblem[] {
  const given = parts.filter((part) => (typed[part] ?? "") !== "");
  if (given.length === 0 || given.length === parts.length) {
    return [];
  }
  return parts
    .filter((part) => (typed[part] ?? "") === "")
    .map((part) => ({
      field: part,
      code: "blank",
      message: `Paste ${part} too: every part of the secret is saved at once, or leave them all empty to keep the ones held.`,
    }));
}

/** The body of one set-up, as `brain.channel_routes.ChannelAsked` declares it. */
export function setupBody(
  enabled: boolean,
  fields: readonly string[],
  values: Readonly<Record<string, string>>,
  secret: string,
  parts: Readonly<Record<string, string>> = {},
  required: readonly string[] = fields,
): { enabled: boolean; tenant: Record<string, string>; secret?: string; secret_parts?: Record<string, string> } {
  const tenant: Record<string, string> = {};
  for (const field of fields) {
    const value = (values[field] ?? "").trim();
    // A blank field nobody requires is left out, so a path that does not ask for it saves without it.
    if (value !== "" || required.includes(field)) {
      tenant[field] = value;
    }
  }
  const typed = Object.values(parts).some((one) => one !== "");
  if (typed) {
    return { enabled, tenant, secret_parts: { ...parts } };
  }
  return secret === "" ? { enabled, tenant } : { enabled, tenant, secret };
}

export const TEST_OUTCOMES: Readonly<Record<string, string>> = {
  sent: "Sent.",
  refused: "Not sent.",
  unknown: "Not known whether it arrived.",
};

/** The filters the bindings route declares that the card offers, over values on rows drawn. */
export const BOUND_FILTERS: readonly FilterChoice<BoundRow>[] = [
  { column: "principal_id", label: "Person", everything: "Everyone bound", read: (row) => row.principal_id },
];

/** The orders the card offers, as the route spells them. Empty is the route's own, by name. */
export const BOUND_SORTS: readonly SortChoice[] = [
  { value: "", label: "By name" },
  { value: "-bound_at", label: "Most recently bound first" },
];
