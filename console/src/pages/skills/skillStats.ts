/**
 * One skill's figures, from the stats route every module shares (`agents/agentStats.ts`' path).
 *
 * **`GET /api/v1/console/skills/{name}/stats`**, served by `brain.console_stats_routes` (the stats
 * package): how many of the reader's agents are pinned to the skill (`agents_pinned`), at how many
 * versions between them (`pinned_versions`), how many versions the library holds (`versions`, null
 * for a reader the library is not listed to), the versions added in each period, and `unrecorded`,
 * the figures nothing on an install records yet with the reason: runs that used it and its last use
 * (`brain.console.entity_stats.SKILL_RUNS_ARE_NOT_RECORDED`).
 *
 * **A figure the route does not send, or lists as unrecorded, is "Not recorded yet" with its
 * reason, never nought.** `kit/KpiStrip.tsx`' rule. A null, a string, a negative or a fraction in a
 * count's place is no figure.
 *
 * Task ids: M27.16.1
 */

import { statsApiPath } from "../agents/agentStats";

export const SKILLS_MODULE = "skills";

/** The figure `unrecorded` names runs by, and last use. */
export const RUNS_FIGURE = "runs_that_used_it";
export const LAST_USED_FIGURE = "last_used";

export function skillStatsApiPath(name: string): string {
  return statsApiPath(SKILLS_MODULE, name);
}

export interface SkillPeriod {
  readonly range: string;
  readonly versionsAdded?: number;
}

export interface SkillStats {
  readonly agentsPinned?: number;
  readonly pinnedVersions?: number;
  readonly versions?: number;
  readonly periods: readonly SkillPeriod[];
  readonly unrecorded: readonly { readonly figure: string; readonly why: string }[];
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `counted` or `said`.
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Fields) : null;
}

function counted(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

/** The figures out of a body, or null when the body is not an object at all. */
export function readSkillStats(payload: unknown): SkillStats | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const agentsPinned = counted(fields["agents_pinned"]);
  const pinnedVersions = counted(fields["pinned_versions"]);
  const versions = counted(fields["versions"]);
  const seen = new Set<string>();
  const periods: SkillPeriod[] = [];
  for (const one of listOf(fields["periods"])) {
    const period = fieldsOf(one);
    const range = said(period?.["range"]);
    if (period === null || range === undefined || seen.has(range)) {
      continue;
    }
    seen.add(range);
    const versionsAdded = counted(period["versions_added"]);
    periods.push({ range, ...(versionsAdded === undefined ? {} : { versionsAdded }) });
  }
  const unrecorded: { figure: string; why: string }[] = [];
  for (const one of listOf(fields["unrecorded"])) {
    const row = fieldsOf(one);
    const figure = said(row?.["figure"]);
    const why = said(row?.["why"]);
    if (figure !== undefined && why !== undefined) {
      unrecorded.push({ figure, why });
    }
  }
  return {
    ...(agentsPinned === undefined ? {} : { agentsPinned }),
    ...(pinnedVersions === undefined ? {} : { pinnedVersions }),
    ...(versions === undefined ? {} : { versions }),
    periods,
    unrecorded,
  };
}

/** One period's figures, or the first sent when that period was not. */
export function skillPeriod(stats: SkillStats | null, range: string): SkillPeriod | undefined {
  return stats?.periods.find((one) => one.range === range) ?? stats?.periods[0];
}

/** Why a figure is not recorded, when the route said so. */
export function skillUnrecordedWhy(stats: SkillStats | null, figure: string): string | undefined {
  return stats?.unrecorded.find((one) => one.figure === figure)?.why;
}
