/**
 * What the Agents pages ask the API before they switch an agent on or off, archive it, duplicate
 * it or hand it on, and what they send. No React.
 *
 * `brain.agent_lifecycle_routes` serves the five moves and `GET /agents/{id}/lifecycle`, and this file
 * names the same addresses. **Each move sends what the page drew**: the state for a switch or an
 * archive, the steward for a hand-over, and the configuration digest for a duplicate. The route
 * compares it with the row and answers a page that went stale with a 409 and a sentence, and writes
 * nothing, so this file holds no rule about what may move: it reads what the API said and builds
 * the body from it.
 *
 * **The words a person confirms are the domain's.** A switch keeps everything the agent holds, an
 * archive is for good (`brain.agents.lifecycle.ARCHIVE_IS_TERMINAL`), a hand-over moves who answers
 * for the agent and not what it may reach (`A_TRANSFER_MOVES_THE_STEWARD_AND_NOT_THE_REACH`), and a
 * copy starts disabled and at Shadow (`STARTS_DISABLED_AT_SHADOW`). A refusal is the API's own
 * sentence, read by `readNotChanged`, never one written here.
 *
 * **The channels an agent answers on are read here too** (M13.7.4), because the same route serves them
 * and its steward may switch them without holding either authority over the row. The page sends the
 * channels it drew as `expected`, the same stale-page check as every move.
 *
 * Task ids: M27.11.6, M27.11.7, M13.7.4
 */

import { readChannelChoices, type ChannelChoice } from "./agents/agentDraftsQuery";

export { readNotChanged } from "./agentAutomationsQuery";

/** The acts the pages offer. */
export type LifecycleAct = "enable" | "disable" | "archive" | "duplicate" | "transfer";

function under(agentId: string, verb: string): string {
  return `/agents/${encodeURIComponent(agentId)}/${verb}`;
}

/** `brain.agent_lifecycle_routes.LIFECYCLE_PATH`. */
export function agentLifecycleApiPath(agentId: string): string {
  return under(agentId, "lifecycle");
}

/** `ENABLE_PATH`, `DISABLE_PATH`, `ARCHIVE_PATH`, `TRANSFER_PATH` and `DUPLICATE_PATH`, by act. */
export function agentMoveApiPath(agentId: string, act: LifecycleAct): string {
  return under(agentId, act);
}

/** `brain.agent_lifecycle_routes.CHANNELS_PATH`. */
export function agentChannelsApiPath(agentId: string): string {
  return under(agentId, "channels");
}

/** One agent as a reader who may act on it sees it: `LifecycleView`. */
export interface AgentLifecycle {
  readonly agentId: string;
  readonly displayName: string;
  readonly state: string;
  readonly ownerId: string;
  readonly effectiveHash?: string;
  readonly mayChange: boolean;
  readonly mayDuplicate: boolean;
  readonly duplicateUnavailable?: string;
  /** The channels it answers on now, as stored. */
  readonly channels: readonly string[];
  /** Every channel it could answer on, as boxes, in the API's order. */
  readonly channelChoices: readonly ChannelChoice[];
  /** The sentence that an agent with no channel ticked answers nowhere. */
  readonly channelsNote: string;
  readonly mayChangeChannels: boolean;
  /** Each channel with an adapter this reader is offered, and how the agent answers there (M39.2.4.1). */
  readonly channelRows: readonly ChannelRow[];
}

/** `ChannelRowView`: one adapter's channel, whether the agent answers there and how. */
export interface ChannelRow {
  readonly name: string;
  readonly label: string;
  readonly enabled: boolean;
  /** `card`, `attachment` or `plain`, chosen from the adapter's own declaration. */
  readonly profile: string;
  readonly groupInstallable: boolean;
}

/** How an answer is laid out on a channel, in words. A profile the page does not know is said as text. */
export const PROFILE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  card: "answers as cards with buttons",
  attachment: "answers as text with files attached",
  plain: "answers as plain text",
});

/** The rows out of a response body: only well-formed ones, in the API's order. */
export function readChannelRows(value: unknown): readonly ChannelRow[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((one: unknown) => {
    if (typeof one !== "object" || one === null) {
      return [];
    }
    const row = one as Readonly<Record<string, unknown>>;
    const name = said(row["name"]);
    const label = said(row["label"]);
    const profile = said(row["profile"]);
    if (name === undefined || label === undefined || profile === undefined) {
      return [];
    }
    return [{ name, label, enabled: row["enabled"] === true, profile, groupInstallable: row["group_installable"] === true }];
  });
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

/** The lifecycle out of a response body, or null when the body is not one. */
export function readLifecycle(payload: unknown): AgentLifecycle | null {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said` or a boolean check below.
  const fields = payload as Readonly<Record<string, unknown>>;
  const agentId = said(fields["agent_id"]);
  const displayName = said(fields["display_name"]);
  const state = said(fields["state"]);
  const ownerId = said(fields["owner_id"]);
  if (agentId === undefined || displayName === undefined || state === undefined || ownerId === undefined) {
    return null;
  }
  const effectiveHash = said(fields["effective_hash"]);
  const duplicateUnavailable = said(fields["duplicate_unavailable"]);
  return {
    agentId,
    displayName,
    state,
    ownerId,
    ...(effectiveHash === undefined ? {} : { effectiveHash }),
    mayChange: fields["may_change"] === true,
    mayDuplicate: fields["may_duplicate"] === true,
    ...(duplicateUnavailable === undefined ? {} : { duplicateUnavailable }),
    channels: Array.isArray(fields["channels"])
      ? fields["channels"].filter((one): one is string => said(one) !== undefined)
      : [],
    channelChoices: readChannelChoices(fields["channel_choices"]),
    channelsNote: said(fields["channels_note"]) ?? "",
    mayChangeChannels: fields["may_change_channels"] === true,
    channelRows: readChannelRows(fields["channel_rows"]),
  };
}

/**
 * The body a channel switch sends: the ticked names in the order the boxes are offered, and the
 * channels the page drew, which the route compares with the row.
 */
export function channelsBody(shown: AgentLifecycle, chosen: ReadonlySet<string>): Record<string, unknown> {
  return {
    channels: shown.channelChoices.filter((one) => chosen.has(one.name)).map((one) => one.name),
    expected: [...shown.channels],
  };
}

/** What each stored channel is called, from the boxes the API sent; a name it did not label is its own name. */
export function channelLabels(shown: AgentLifecycle): string[] {
  const labels = new Map(shown.channelChoices.map((one) => [one.name, one.label]));
  return shown.channels.map((name) => labels.get(name) ?? name);
}

/** The acts a lifecycle word offers, before anybody asks who may press them. */
export function actsFor(state: string | undefined): readonly LifecycleAct[] {
  if (state === "enabled") {
    return ["disable", "archive"];
  }
  if (state === "disabled") {
    return ["enable", "archive"];
  }
  return [];
}

/** The body each move sends: what the page drew, and for a copy or a hand-over what was typed. */
export function moveBody(act: LifecycleAct, shown: AgentLifecycle, typed: string): Record<string, unknown> {
  if (act === "transfer") {
    return { to_owner: typed.trim(), expected_owner: shown.ownerId };
  }
  if (act === "duplicate") {
    return { display_name: typed.trim(), expected_hash: shown.effectiveHash ?? "" };
  }
  return { expected_state: shown.state };
}

/** What each act is called, on a menu and on the button that does it. */
export const ACT_LABELS: Readonly<Record<LifecycleAct, string>> = Object.freeze({
  enable: "Switch on",
  disable: "Switch off",
  archive: "Archive",
  duplicate: "Duplicate",
  transfer: "Hand to a new steward",
});

/** What happens, said before it happens. */
export const ACT_CONSEQUENCES: Readonly<Record<LifecycleAct, string>> = Object.freeze({
  enable: "It can be chosen again and answers the people who can find it. What it may reach does not change.",
  disable: "It stops being chosen and keeps everything it holds. It can be switched on again.",
  archive: "It stops at once and for good, and keeps its history. An archived agent cannot be switched on again.",
  duplicate:
    "A new agent is made from the same version with the same settings. It starts disabled and at Shadow, " +
    "and only you can find it.",
  transfer: "The new steward answers for it from now on. What it may reach and who can find it do not change.",
});

/** What a person types, for the two acts that need a word from them. */
export const TYPED_LABELS: Readonly<Partial<Record<LifecycleAct, string>>> = Object.freeze({
  duplicate: "Name for the copy",
  transfer: "The new steward's person id",
});

/** Said when that field is left blank, and nothing is sent. */
export const TYPED_MISSING: Readonly<Partial<Record<LifecycleAct, string>>> = Object.freeze({
  duplicate: "Give the copy a name before making it.",
  transfer: "Say who takes this agent before handing it on.",
});

/** The question a person answers, naming the agent. */
export function actQuestion(act: LifecycleAct, name: string): string {
  const verbs: Readonly<Record<LifecycleAct, string>> = {
    enable: "Switch on",
    disable: "Switch off",
    archive: "Archive",
    duplicate: "Duplicate",
    transfer: "Hand on",
  };
  return `${verbs[act]} ${name}?`;
}

/** What the page says once a move is done. */
export const ACT_DONE: Readonly<Record<LifecycleAct, string>> = Object.freeze({
  enable: "Switched on",
  disable: "Switched off",
  archive: "Archived",
  duplicate: "Duplicated",
  transfer: "Handed on",
});

/** Said when the reader may not do the act they chose, from what the API said about them. */
export const MAY_NOT_CHANGE = "You cannot change this agent: your authority does not reach it.";
