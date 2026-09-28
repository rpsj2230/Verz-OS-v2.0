/**
 * What can be done to a skill from its pages, the words each state is drawn in, and for each act
 * with no route the one sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes, not the design.** On 2026-09-28 `brain.skill_routes` served adding
 * by paste or upload, importing from GitHub or an address, saving an edit as a new version, setting
 * categories, approving or rejecting (a decision by the person who added it recorded as theirs),
 * assigning to an agent, and, new with this page, retiring and reinstating a version and detaching a
 * skill from an agent. Every one of those is a live control. What is left is trying a skill out
 * through an agent in practice mode, which `docs/admin-console-architecture.md` 4.2 says is tested
 * through an agent that holds it and which no route runs; it is drawn as `kit/UnavailableAction`
 * with the sentence below, and `tests/skills-module.test.tsx` fails the day its route lands.
 *
 * **A skill is never deleted.** A version is retired, which keeps it and its history; that is the
 * product's rule (`brain.console.skill_library.A_RETIRED_VERSION_IS_KEPT_AND_ONLY_REFUSED_TO_NEW_AGENTS`),
 * so there is no delete control drawn, disabled or otherwise.
 *
 * Task ids: M27.16.1, M27.11.8
 */

/** Why each act with no route cannot be pressed, and the API path whose arrival retires it. */
export const UNAVAILABLE = Object.freeze({
  tryOut: {
    reason:
      "Coming soon: trying a skill out through an agent in practice mode, as a named person, before it is assigned for real.",
    retiredBy: /^\/api\/v1\/(skills\/\{[^}]+\}\/(rehearsal|trial)|agents\/\{[^}]+\}\/rehearse)\b/,
  },
});

export type UnavailableAct = keyof typeof UNAVAILABLE;

/** Where related work is done, as console addresses. */
export const WORKS_AT = Object.freeze({
  skills: "/skills",
  agents: "/agents",
  tools: "/tools",
  audit: "/audit",
});

/** What each review state reads as on a pill. `brain.console.agent_tabs.Review`'s four words. */
export const REVIEW_PILL: Readonly<Record<string, string>> = Object.freeze({
  pending: "Waiting for review",
  approved: "Approved",
  rejected: "Rejected",
  changed: "Changed since approval",
});

export function reviewPill(review: string): string {
  return REVIEW_PILL[review] ?? review;
}

export const RETIRED_WORD = "Retired";

/** How the retired filter's two values read. */
export function retiredWords(value: string): string {
  return value === "true" ? RETIRED_WORD : "In the library";
}

/** Where a skill came from, in a word. */
export const SOURCE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  upload: "Pasted or uploaded",
  github: "GitHub repository",
  url: "Web address",
});

export function sourceWord(source: string): string {
  return SOURCE_WORDS[source] ?? source;
}
