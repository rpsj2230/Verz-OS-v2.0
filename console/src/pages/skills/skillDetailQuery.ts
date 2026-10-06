/**
 * What one skill's page asks for and how it reads the answers. No React.
 *
 * **One skill is resolved against the Skills page's own answer**, `GET /skills` filtered to the
 * name, and never against a route answering one skill by name for reading, which
 * `brain.skill_routes` rejects for `A_DEEP_LINK_RESOLVED_AGAINST_THE_PAGE_CANNOT_BE_AN_ORACLE`'s
 * reason. A name nobody may see and a name that does not exist are the same empty answer, and the
 * page draws the same sentence for both.
 *
 * **The history is the audit ledger's**, read through `GET /audit` exactly as the Activity screen
 * reads it, so an entry this reader may not see is absent here too: the skill's own entries by
 * subject, and the assignments and detachments recorded about agents under the skill's folded name.
 * A reader the Activity screen does not open for is told where the history is kept, and nothing
 * about what it holds.
 *
 * Task ids: M27.16.1, M27.15.55
 */

import { AUDIT_API_PATH, type AuditRow } from "../auditQuery";
import type { AgentChoice, LibrarySkill, SkillLibraryRow } from "../skillsQuery";
import { personWords, readSkillsPage, skillApiPath, skillIn, versionsOf } from "../skillsQuery";

export { skillApiPath };

/** The three views, in the owner's order. The first is where the bare address lands. */
export const VIEWS = ["dashboard", "profile", "about"] as const;
export type SkillView = (typeof VIEWS)[number];

export const VIEW_LABELS: Readonly<Record<SkillView, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

/** Which view an address opens. Anything else opens the Dashboard, silently. */
export function viewFor(view: string | undefined): SkillView {
  return view === "profile" || view === "about" ? view : "dashboard";
}

/** One skill as its page holds it. */
export interface SkillDetail {
  readonly name: string;
  /** Every version, newest first, as the API ordered the library. */
  readonly versions: readonly LibrarySkill[];
  /** The agents this reader may see running it, with the bytes each runs. */
  readonly pinned: SkillLibraryRow | null;
  /** The agents this reader may give a skill to or take one off. */
  readonly agents: readonly AgentChoice[];
  /** The agents a reviewer may rehearse a waiting version through (M12.3.4). */
  readonly rehearsalAgents: readonly AgentChoice[];
  readonly registryIsAbsent: boolean;
}

/** The skill out of the page's answer, or null when nothing here names it. */
export function readSkillDetail(payload: unknown, name: string): SkillDetail | null {
  const page = readSkillsPage(payload);
  const versions = versionsOf(page.library, name);
  const pinned = skillIn(page.skills, name);
  if (versions.length === 0 && pinned === null) {
    return null;
  }
  return {
    name,
    versions,
    pinned,
    agents: page.agents,
    rehearsalAgents: page.rehearsalAgents,
    registryIsAbsent: page.registryIsAbsent,
  };
}

/** The version the header speaks for: the newest that is not retired, or the newest of all. */
export function headlineVersion(detail: SkillDetail): LibrarySkill | undefined {
  return detail.versions.find((one) => one.retired !== true) ?? detail.versions[0];
}

/** The name the ledger records an assignment of this skill under. `ledger_reference`. */
export function ledgerReference(name: string): string {
  return name.replace(/-/g, "_");
}

/** The two reads the history is made of: the skill's own entries, and its assignments. */
export function historyApiPaths(name: string): readonly [string, string] {
  const own = new URLSearchParams({ subject_kind: "skill", q: name, limit: "50" });
  const assigned = new URLSearchParams({ action: "compose_change", q: ledgerReference(name), limit: "50" });
  return [`${AUDIT_API_PATH}?${own.toString()}`, `${AUDIT_API_PATH}?${assigned.toString()}`];
}

/** One line of the history. */
export interface HistoryLine {
  readonly at: string;
  readonly words: string;
  readonly by?: string;
}

const SKILL_CHANGES: Readonly<Record<string, string>> = Object.freeze({
  imported: "Added",
  edited: "Saved as a new version",
  approved: "Approved",
  rejected: "Rejected",
  self_approved: "Approved by the person who added it",
  self_rejected: "Rejected by the person who added it",
  categorised: "Categories changed",
  retired: "Retired",
  reinstated: "Reinstated",
});

function detail(row: AuditRow, key: string): string | undefined {
  const value = (row.details as Readonly<Record<string, unknown>>)[key];
  return typeof value === "string" ? value : undefined;
}

/**
 * The history out of the two ledger answers, newest first.
 *
 * Only this skill's rows are kept, matched exactly rather than by the search that fetched them. A
 * version is named by its number when the page holds it; a person by the name the page already
 * shows for them, and otherwise not at all, because an identifier is not a name.
 */
export function readHistory(
  own: readonly AuditRow[],
  assigned: readonly AuditRow[],
  detail_: SkillDetail,
): readonly HistoryLine[] {
  const versions = new Map(detail_.versions.map((one) => [one.digest, one.version]));
  const people = new Map<string, string>();
  for (const one of detail_.versions) {
    if (one.submitted_by_name) {
      people.set(one.submitted_by, one.submitted_by_name);
    }
    if (one.reviewer && one.reviewer_name) {
      people.set(one.reviewer, one.reviewer_name);
    }
  }
  const agents = new Map<string, string>(detail_.agents.map((one) => [one.agent_id, one.display_name]));
  for (const pin of detail_.pinned?.pinned_by ?? []) {
    if (pin.display_name) {
      agents.set(pin.agent_id, pin.display_name);
    }
  }
  const lines: HistoryLine[] = [];
  for (const row of own) {
    if (row.subject_kind !== "skill" || row.subject_id !== detail_.name) {
      continue;
    }
    const change = detail(row, "change");
    const said = change === undefined ? undefined : SKILL_CHANGES[change];
    if (said === undefined) {
      continue;
    }
    const digest = detail(row, "digest");
    const version = digest === undefined ? undefined : versions.get(digest);
    const by = people.get(row.actor_id);
    lines.push({ at: row.at, words: version === undefined ? said : `${said}: version ${version}`, ...(by === undefined ? {} : { by }) });
  }
  const reference = ledgerReference(detail_.name);
  for (const row of assigned) {
    if (row.subject_kind !== "agent" || detail(row, "part") !== "skills" || detail(row, "reference") !== reference) {
      continue;
    }
    const agent = agents.get(row.subject_id) ?? "an agent";
    const reason = detail(row, "reason_code");
    const words =
      detail(row, "direction") === "attached"
        ? `Assigned to ${agent}`
        : reason === "skill_replace"
          ? `Replaced on ${agent} by another version`
          : `Detached from ${agent}`;
    const by = people.get(row.actor_id);
    lines.push({ at: row.at, words, ...(by === undefined ? {} : { by }) });
  }
  return lines.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}

/** A person's name for the page, or a plain word. */
export function named(name: string | null | undefined, otherwise: string): string {
  return personWords(name, otherwise);
}

/** An instant as a day, in the reader's own time zone. */
export function dayWords(at: string | null | undefined): string {
  if (at === null || at === undefined) {
    return "";
  }
  const parsed = Date.parse(at);
  return Number.isNaN(parsed)
    ? ""
    : new Date(parsed).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
