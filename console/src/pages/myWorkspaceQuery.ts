/**
 * What My workspace asks the API for and how its figures are read. No React.
 *
 * `brain.mine_routes` answers, for the person asking and nobody else: the route takes no parameter
 * naming a person, so there is nothing here that could ask about somebody else. The decisions are
 * `brain.console.own_things`, `brain.member_activity` and `brain.console.govern_estate.
 * subject_memory`'s, and this module only turns what they sent into what SCREEN 12 draws.
 *
 * **A budget that was not read is not a budget of nothing.** `budget` is null exactly when the API
 * could not read every run of the month and says why, and `readBudget` returns that as a value the
 * page cannot draw as full headroom, which is `installQuery.ts`' `readRecovery` rule.
 *
 * **Money is minor units, shown as `spendQuery.majorUnits` shows it**, because nothing on an
 * install says which currency a ceiling is in and the Spend screen already decided how to draw one.
 *
 * Task ids: M27.7.28
 */

import type { components } from "../api/schema";
import { wasRead, type Read } from "./installQuery";
import { majorUnits } from "./spendQuery";

export type Workspace = components["schemas"]["MineWorkspaceView"];
export type MyAgent = components["schemas"]["MineAgentView"];
export type MyCeiling = components["schemas"]["MineCeilingView"];
export type MyItem = components["schemas"]["MineItemView"];
export type Learned = components["schemas"]["MineLearnedView"];

export const WORKSPACE_API_PATH = "/me/workspace";

export { wasRead };

/** The ceilings, or why none could be read. */
export function readBudget(payload: Workspace): Read<readonly MyCeiling[]> {
  return payload.budget === null ? { unread: payload.budget_unread } : { panel: payload.budget };
}

/** The ceiling SCREEN 12's budget figure is about: the month's, or none. */
export function monthly(ceilings: readonly MyCeiling[]): MyCeiling | null {
  return ceilings.find((one) => one.period === "month") ?? null;
}

/** "18.00 of 40.00, 45%". A whole percent of the ceiling spent, rounded up, so the figure never
 * reads as more headroom than there is. */
export function spentOf(one: MyCeiling): string {
  const percent = Math.ceil((one.spent_minor * 100) / one.ceiling_minor);
  return `${majorUnits(one.spent_minor)} of ${majorUnits(one.ceiling_minor)}, ${String(percent)}%`;
}

/** SCREEN 12's source words: a department's or the company's agent, or one of your own. */
export const PROVISION_WORDS: Readonly<Record<string, string>> = {
  provided: "provided",
  personal: "mine",
};

/** How many of the agents this person can call are their own. A count of their own rows. */
export function ownAgents(agents: readonly MyAgent[]): number {
  return agents.filter((one) => one.provision === "personal").length;
}

/** Where an agent runs, in words, or a sentence when no surface may carry this person's run. */
export function whereItRuns(agent: MyAgent): string {
  return agent.channels.length === 0 ? "no surface you can use" : agent.channels.join(", ");
}
