/**
 * What an agent's page asks the API about a newer version of its template, and what it sends. No
 * React.
 *
 * `brain.agent_upgrade_routes` serves the review, the acceptance and the decline, and this file
 * names the same addresses. **Each write sends what the page drew**: the version on offer and the
 * configuration digest the review was read against. The route compares both with what is there and
 * answers a page that went stale with a 409 and a sentence, and writes nothing, so this file holds no
 * rule about what may be upgraded: it reads what the API said and builds the body from it.
 *
 * **Every conflict is answered, and by the person.** A path this install had claimed and the new
 * version moves is a choice between two values in front of them, keep ours or take the version's,
 * and the body carries exactly the paths the review listed, none defaulted. A merge of the two was
 * rejected in the domain (`brain.agents.upgrade.Resolution`) and is not offered here either.
 *
 * **A version the API says cannot be accepted is shown with the reason and still declinable.** The
 * reason is the API's own sentence, read from `accept_unavailable`, never one written here, and a
 * decline is allowed whatever stops an acceptance.
 *
 * Task ids: M13.4.2, M13.4.3, M13.4.4, M13.4.5
 */

export { readNotChanged } from "../agentAutomationsQuery";

/** `brain.agent_upgrade_routes.UPGRADE_PATH`. */
export function agentUpgradeApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/upgrade`;
}

/** `ACCEPT_PATH`. */
export function agentUpgradeAcceptApiPath(agentId: string): string {
  return `${agentUpgradeApiPath(agentId)}/accept`;
}

/** `DECLINE_PATH`. */
export function agentUpgradeDeclineApiPath(agentId: string): string {
  return `${agentUpgradeApiPath(agentId)}/decline`;
}

/** The two answers a conflict has. There is no third. */
export type Resolution = "keep_local" | "take_template";

export const RESOLUTION_LABELS: Readonly<Record<Resolution, string>> = Object.freeze({
  keep_local: "Keep what we have here",
  take_template: "Use the new version's",
});

/** Who last set a value, and when. */
export interface UpgradeOwner {
  readonly setBy: string;
  readonly setAt: string;
}

/** One path this install claimed and the new version moves: the three columns. */
export interface UpgradeConflict {
  readonly path: string;
  readonly where: string;
  readonly was: unknown;
  readonly now: unknown;
  readonly local: unknown;
  readonly owner: UpgradeOwner;
}

/** One path the new version moves that nothing here claimed. */
export interface UpgradeChange {
  readonly path: string;
  readonly where: string;
  readonly was: unknown;
  readonly now: unknown;
  readonly sealed: boolean;
}

/** What is waiting for one agent: `UpgradeView`. */
export interface AgentUpgrade {
  readonly agentId: string;
  readonly displayName: string;
  /** `current`, `available` or `declined`. */
  readonly badge: string;
  readonly fromVersion: number;
  readonly toVersion?: number;
  readonly expectedHash?: string;
  readonly conflicts: readonly UpgradeConflict[];
  readonly updates: readonly UpgradeChange[];
  readonly acceptUnavailable?: string;
  readonly nothing?: string;
}

function fieldsOf(payload: unknown): Readonly<Record<string, unknown>> | null {
  // A cast at the boundary, where proving a structural match buys nothing: every field read from
  // the result is checked below.
  return typeof payload === "object" && payload !== null && !Array.isArray(payload)
    ? (payload as Readonly<Record<string, unknown>>)
    : null;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function whole(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) ? value : undefined;
}

function readOwner(payload: unknown): UpgradeOwner | null {
  const fields = fieldsOf(payload);
  const setBy = said(fields?.["set_by"]);
  const setAt = said(fields?.["set_at"]);
  return setBy === undefined || setAt === undefined ? null : { setBy, setAt };
}

function readConflicts(payload: unknown): readonly UpgradeConflict[] {
  if (!Array.isArray(payload)) {
    return [];
  }
  const found: UpgradeConflict[] = [];
  for (const row of payload as readonly unknown[]) {
    const fields = fieldsOf(row);
    const path = said(fields?.["path"]);
    const owner = readOwner(fields?.["owner"]);
    if (fields === null || path === undefined || owner === null) {
      continue;
    }
    found.push({
      path,
      where: said(fields["where"]) ?? path,
      was: fields["was"],
      now: fields["now"],
      local: fields["local"],
      owner,
    });
  }
  return found;
}

function readChanges(payload: unknown): readonly UpgradeChange[] {
  if (!Array.isArray(payload)) {
    return [];
  }
  const found: UpgradeChange[] = [];
  for (const row of payload as readonly unknown[]) {
    const fields = fieldsOf(row);
    const path = said(fields?.["path"]);
    if (fields === null || path === undefined) {
      continue;
    }
    found.push({
      path,
      where: said(fields["where"]) ?? path,
      was: fields["was"],
      now: fields["now"],
      sealed: fields["sealed"] === true,
    });
  }
  return found;
}

/** The review out of a response body, or null when the body is not one. */
export function readUpgrade(payload: unknown): AgentUpgrade | null {
  const fields = fieldsOf(payload);
  const agentId = said(fields?.["agent_id"]);
  const displayName = said(fields?.["display_name"]);
  const badge = said(fields?.["badge"]);
  const fromVersion = whole(fields?.["from_version"]);
  if (
    fields === null ||
    agentId === undefined ||
    displayName === undefined ||
    badge === undefined ||
    fromVersion === undefined
  ) {
    return null;
  }
  const toVersion = whole(fields["to_version"]);
  const expectedHash = said(fields["expected_hash"]);
  const acceptUnavailable = said(fields["accept_unavailable"]);
  const nothing = said(fields["nothing"]);
  return {
    agentId,
    displayName,
    badge,
    fromVersion,
    ...(toVersion === undefined ? {} : { toVersion }),
    ...(expectedHash === undefined ? {} : { expectedHash }),
    conflicts: readConflicts(fields["conflicts"]),
    updates: readChanges(fields["updates"]),
    ...(acceptUnavailable === undefined ? {} : { acceptUnavailable }),
    ...(nothing === undefined ? {} : { nothing }),
  };
}

/** Whether there is a version to show at all: one on offer, accepted or turned away. */
export function hasAnOffer(upgrade: AgentUpgrade | null): upgrade is AgentUpgrade & {
  readonly toVersion: number;
  readonly expectedHash: string;
} {
  return (
    upgrade !== null &&
    upgrade.badge !== "current" &&
    upgrade.toVersion !== undefined &&
    upgrade.expectedHash !== undefined
  );
}

/** The body an acceptance sends: the version and digest drawn, and one answer per conflict. */
export function acceptBody(
  upgrade: AgentUpgrade & { readonly toVersion: number; readonly expectedHash: string },
  chosen: Readonly<Record<string, Resolution>>,
): Record<string, unknown> {
  return {
    to_version: upgrade.toVersion,
    expected_hash: upgrade.expectedHash,
    resolutions: Object.fromEntries(upgrade.conflicts.map((one) => [one.path, chosen[one.path]])),
  };
}

/** The body a decline sends: the version and digest drawn. */
export function declineBody(
  upgrade: AgentUpgrade & { readonly toVersion: number; readonly expectedHash: string },
): Record<string, unknown> {
  return { to_version: upgrade.toVersion, expected_hash: upgrade.expectedHash };
}

/** Whether every conflict has been answered, which is what lets an acceptance be pressed. */
export function allAnswered(upgrade: AgentUpgrade, chosen: Readonly<Record<string, Resolution>>): boolean {
  return upgrade.conflicts.every((one) => chosen[one.path] !== undefined);
}

/** A value as a person reads it: words as they are, lists joined, anything else spelled out. */
export function valueWords(value: unknown): string {
  if (value === null || value === undefined) {
    return "nothing";
  }
  if (typeof value === "string") {
    return value === "" ? "nothing" : value;
  }
  if (Array.isArray(value)) {
    const parts = (value as readonly unknown[]).map(valueWords);
    return parts.length === 0 ? "nothing" : parts.join(", ");
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export const UPGRADE_HEADING = "A newer version of this agent's template";
export const ACCEPT_LABEL = "Upgrade";
export const DECLINE_LABEL = "Not this version";
export const KEEP_LABEL = "Not now";
export const ANSWER_EVERY_CONFLICT = "Choose an answer for every change above before upgrading.";
export const ACCEPT_CONSEQUENCE =
  "The agent moves to the new version, with the answers you chose. It keeps its steward, who can find " +
  "it, where it answers and whether it is switched on, unless the new version needs something this " +
  "install does not have yet, in which case it is switched off.";
export const DECLINE_CONSEQUENCE =
  "This version will not be offered again for this agent. A newer one will be. You can still " +
  "upgrade to it from here later.";
export const DONE_UPGRADED = "Upgraded";
export const DONE_DECLINED = "Declined";
export const NOT_CHANGED = "Nothing was changed";
export const SOMETHING_DID_NOT_WORK = "Something did not work";
