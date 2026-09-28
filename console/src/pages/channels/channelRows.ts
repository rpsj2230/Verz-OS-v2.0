/**
 * The Channels module's rows: where the list and one channel's row are read, how a row reads, and
 * the words for each state. No React.
 *
 * **One row shape for the list and for a channel's own page.** `GET /api/v1/console/channels` is the
 * module list on `brain.listing`'s convention, and `GET /api/v1/console/channels/{name}` is one row
 * of it, both from `brain.binding_routes`, so the page and the list cannot disagree about a channel.
 * A channel the reader may not manage is no row, and its page is the one 404 a name that is no
 * channel gets; nothing here says which.
 *
 * **A person is a name.** The row carries who last changed the record by name, and their id for the
 * Advanced section; a name the directory no longer holds reads as "someone no longer listed" rather
 * than as the id.
 *
 * Task ids: M27.13.1, M27.16.1
 */

import type { components } from "../../api/schema";
import type { FilterChoice, SortChoice } from "../../components/listing";
import { healthWord } from "../channelsQuery";

export type ChannelRow = components["schemas"]["ChannelRowView"];

/** The module list and one channel's row, under the API base. */
export const CHANNEL_LIST_API_PATH = "/console/channels";

export function channelRowApiPath(name: string): string {
  return `${CHANNEL_LIST_API_PATH}/${encodeURIComponent(name)}`;
}

/** The console addresses. */
export const CHANNELS_ADDRESS = "/channels";

export function channelAddress(name: string): string {
  return `${CHANNELS_ADDRESS}/${encodeURIComponent(name)}`;
}

export const STATUS_WORDS: Readonly<Record<string, string>> = Object.freeze({
  on: "On",
  off: "Off",
  not_set_up: "Not set up",
});

export const SECRET_WORDS: Readonly<Record<string, string>> = Object.freeze({
  held: "Held",
  not_held: "Not held",
  unknown: "Not known",
  none: "None kept",
});

/** Why a secret is not known, for its tooltip: the vault could not be asked. */
export const SECRET_UNKNOWN_WHY = "The vault could not be asked, so whether a secret is held is not known.";

export const RECEIVES_WORDS: Readonly<Record<string, string>> = Object.freeze({
  true: "Received here",
  false: "Not received yet",
});

export function statusWords(status: string): string {
  return STATUS_WORDS[status] ?? status;
}

export function secretWords(secret: string): string {
  return SECRET_WORDS[secret] ?? secret;
}

/** Who last changed the record, by name, or the sentence for someone the directory does not list. */
export const NOT_LISTED = "someone no longer listed";

export function changedByWords(row: ChannelRow): string | undefined {
  if (row.changed_by === null) {
    return undefined;
  }
  return row.changed_by_name ?? NOT_LISTED;
}

function isRow(value: unknown): value is ChannelRow {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const fields = value as Record<string, unknown>;
  return typeof fields["channel"] === "string" && typeof fields["label"] === "string" && typeof fields["status"] === "string";
}

/** The rows of a list body, keeping only what reads as a row. */
export function readChannelRows(payload: unknown): readonly ChannelRow[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const items = (payload as { items?: unknown }).items;
  return Array.isArray(items) ? items.filter(isRow) : [];
}

/** One row, or null when the body is not one. */
export function readChannelRow(payload: unknown): ChannelRow | null {
  return isRow(payload) ? payload : null;
}

/** The filters the list route declares that the page offers, over values on rows drawn. */
export const CHANNEL_FILTERS: readonly FilterChoice<ChannelRow>[] = [
  { column: "status", label: "Status", everything: "Any status", read: (row) => row.status, describe: statusWords },
  { column: "health", label: "Health", everything: "Any health", read: (row) => row.health, describe: healthWord },
  {
    column: "receives",
    label: "Received",
    everything: "Received or not",
    read: (row) => row.receives,
    describe: (value) => RECEIVES_WORDS[value] ?? value,
  },
];

/** The orders the route declares that the page offers. Empty is the route's own, by name. */
export const CHANNEL_SORTS: readonly SortChoice[] = [
  { value: "", label: "Name" },
  { value: "status", label: "Status" },
  { value: "-last_delivered_at", label: "Last active" },
];
