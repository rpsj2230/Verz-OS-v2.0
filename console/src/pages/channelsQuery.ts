/**
 * What the Channels screen and a person's own channels card ask the API for, and what they may
 * send. No React.
 *
 * **Two sides of one fact, on two screens.** An administrator sees each channel's record, its
 * switch, what its adapter declares it can carry, how it is doing and who is bound on it; a person
 * sees, in My workspace, which chats they may connect and which they have, and asks for the code
 * that connects one. `brain.channel_routes` serves the record, the switch, the test message and
 * the deliveries; `brain.binding_routes` serves the rest; `brain.console.channel_health` decides
 * what the deliveries say; `brain.channels.binding` decides everything about a code.
 *
 * **Nothing here decides who may see or change a channel.** The API answers a reader without the
 * channel's authority, a channel that is not switched on and a name that is no channel with one
 * absence, and this module draws whatever it was sent.
 *
 * **The secret is never read and never shown.** A channel says whether its secret is held, or that
 * the vault could not be asked, and the set-up form sends a new secret once and empties the field
 * whatever came back, for `signInLinksQuery.AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT`'s reason.
 *
 * **A code is shown once, where it was asked for.** The API answers it with `no-store` and keeps
 * only its digest; the card holds it in memory until the page is left and says how long it lasts.
 *
 * Task ids: M10.3.1, M10.3.4, M10.1.2, M10.1.3, M10.1.4
 */

import type { components } from "../api/schema";
import type { FilterChoice, SortChoice } from "../components/listing";

export type ChannelsBody = components["schemas"]["ChannelsView"];
/** Named with its module because `brain.agent_routes` has a `ChannelView` of its own. */
export type ChannelRow = components["schemas"]["brain__channel_routes__ChannelView"];
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

/** The console address. */
export const CHANNELS_PATH = "/channels";

/** Where the API keeps every channel this reader may manage. */
export const CHANNELS_API_PATH = "/channels";
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

/** Whether a secret is held, in words, never anything of the secret. */
export function secretWords(held: boolean | null): string {
  if (held === null) {
    return "The vault could not be asked, so whether a secret is held is not known.";
  }
  return held ? "Held in the vault. It is never shown." : "Not held. Set one below.";
}

/** A channel's health, in the chip's words. */
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

/** A delivery's outcome and reason, as one phrase: "outbound, refused: vendor refused". */
export function deliveryWords(row: DeliveryRow): string {
  const reason = row.reason === null ? "" : `: ${row.reason.replaceAll("_", " ")}`;
  const status = row.vendor_status === null ? "" : ` (${String(row.vendor_status)})`;
  return `${row.direction}, ${row.outcome}${reason}${status}`;
}

/** What a channel's adapter declares, in one sentence. */
export function declaredWords(health: HealthBody): string {
  const features = health.features.length === 0 ? "no features" : health.features.join(", ");
  const label = health.can_carry_label
    ? "It can show a person the label an unchecked answer carries."
    : "It cannot show the label an unchecked answer carries, so it is never sent one.";
  return (
    `Declares ${features}. Carries at most ${health.max_classification} information. ${label}`
  );
}

/** Every tenant field left blank, as the sentence the form says beside it. */
export function setupProblems(fields: readonly string[], values: Readonly<Record<string, string>>): string[] {
  return fields
    .filter((field) => (values[field] ?? "").trim() === "")
    .map((field) => `Fill in ${field}, which this channel needs before it can reply.`);
}

/** A blank destination, as the sentence the test form says. */
export function testProblems(to: string): string[] {
  return to.trim() === "" ? ["Say where the test message goes, in the vendor's terms."] : [];
}

/** The body of one set-up, as `brain.channel_routes.ChannelAsked` declares it. */
export function setupBody(
  enabled: boolean,
  fields: readonly string[],
  values: Readonly<Record<string, string>>,
  secret: string,
): { enabled: boolean; tenant: Record<string, string>; secret?: string } {
  const tenant: Record<string, string> = {};
  for (const field of fields) {
    tenant[field] = (values[field] ?? "").trim();
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
