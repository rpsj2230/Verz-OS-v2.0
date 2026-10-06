/**
 * What can be done to an agent from its pages, and for each act either where it works or the one
 * sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes on main, not against the design.** On 2026-09-28 the API served,
 * for one agent: the roster, the workspace, the About flow, pinning a model, the automation gallery
 * with install, start and stop, the instruction override (`/govern/prompts/{agent_id}`, drawn on the
 * Prompts page) and skill assignment (`/skills/{digest}/assignments`, drawn on the Skills page). It
 * served no route that changes an agent's audience or its leash, previews it as a person, or installs
 * it into a chat group. Each of those is an `UNAVAILABLE` sentence below and is drawn as
 * `kit/UnavailableAction`, so the page shows the act exists and is coming rather than hiding it or
 * faking it. Switching on and off, archiving, duplicating and handing on arrived with
 * `brain.agent_lifecycle_routes` on 2026-09-29 and are live acts (`LifecycleActs.tsx`); creating an
 * agent, editing one as a draft and changing its permissions through that draft arrived with
 * `brain.agent_builder_routes` the same day (`NewAgentPage.tsx`, `DraftStart.tsx`, `DraftPage.tsx`).
 * Switching the channels an agent answers on arrived as `/agents/{id}/channels` on 2026-10-06 and is
 * live on the Profile (`AgentChannels.tsx`); adding an agent to one group chat is a different act,
 * a binding to a room rather than a channel, and is still a sentence.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/agents-page.test.tsx` reads every sentence here against the API document: an act listed as
 * unavailable whose route the document now declares fails, so this table cannot go on saying
 * "coming soon" about something that has arrived.
 *
 * The sentences are for an administrator: plain words, led by "Coming soon:" or "Not available
 * yet:", and no package code, route or internal name.
 *
 * Task ids: M27.10.2, M27.11.6
 */

/** Why each act that has no route cannot be pressed, and the shape of the API path whose arrival retires it. */
export const UNAVAILABLE = Object.freeze({
  chatGroup: {
    reason: "Coming soon: adding an agent to a group chat.",
    retiredBy: /^\/api\/v1\/agents\/\{[^}]+\}\/groups\b/,
  },
  level: {
    reason: "Coming soon: changing who can find this agent.",
    retiredBy: /^\/api\/v1\/agents\/\{[^}]+\}\/(audience|availability)\b/,
  },
  browser: {
    reason: "Not available yet: browser use. It is built and tested, and has never been switched on for any agent.",
    retiredBy: /^\/api\/v1\/agents\/\{[^}]+\}\/browser\b/,
  },
});

export type UnavailableAct = keyof typeof UNAVAILABLE;

/** Where the acts that do work are done, as console addresses. */
export const WORKS_AT = Object.freeze({
  /** The instruction override, on the Prompts page. */
  instructions: "/prompts",
  /** Assigning an approved skill, on the Skills page. */
  skills: "/skills",
  /** The catalogue an agent is installed from. */
  templates: "/agent-templates",
  /** The learning review. */
  learning: "/learning",
  /** Every approval, where one waiting on this agent is decided. */
  approvals: "/approvals",
  /** What each model level tries, set once for every agent. */
  routing: "/routing",
  /** Usage and cost across agents. */
  usage: "/usage",
});

/** A lifecycle word as a person reads it. A word nobody here has heard of is drawn as itself. */
export const STATE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  enabled: "Enabled",
  disabled: "Disabled",
  archived: "Archived",
});

/** A rung as a person reads it. */
export const RUNG_WORDS: Readonly<Record<string, string>> = Object.freeze({
  shadow: "Shadow",
  assisted: "Assisted",
  autonomous: "Autonomous",
});

/** What each rung means, said once wherever rungs are drawn. */
export const RUNGS_EXPLAINED =
  "Autonomous: it acts on its own. Assisted: it prepares the action and waits for a person. Shadow: " +
  "it only practises, and nothing is carried out. An action with no setting is Shadow.";

/** An audience level as a person reads it. */
export const LEVEL_WORDS: Readonly<Record<string, string>> = Object.freeze({
  personal: "Personal: the steward only",
  department: "Department: everyone in it",
  company: "Company: everyone",
});

/** A model size as a person reads it. */
export const TIER_WORDS: Readonly<Record<string, string>> = Object.freeze({
  small: "Small",
  main: "Main",
  heavy: "Heavy",
});

export function stateWords(state: string): string {
  return STATE_WORDS[state] ?? state;
}

export function rungWords(rung: string): string {
  return RUNG_WORDS[rung] ?? rung;
}
