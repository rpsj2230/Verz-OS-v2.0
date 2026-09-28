/**
 * What can be done with a template from its pages, and for each act either where it works or the
 * sentence saying why it cannot be pressed.
 *
 * **Measured against the routes on this branch.** Reading the catalogue and one template, and
 * installing a published version as a new agent (`brain.agent_lifecycle_routes`), are served and
 * live. Authoring a template from an agent through the leak scan and withdrawing a published
 * version have no route: `brain.agents.authoring` holds the scan and nothing calls it over HTTP,
 * and `agent.template_version` is insert-only, so a withdrawal needs somewhere to be recorded
 * first. Each is an `UNAVAILABLE` sentence, and `tests/agent-templates.test.tsx` reads every
 * `retiredBy` against the API document so the sentence goes when the route arrives.
 *
 * Task ids: M27.11.7, M27.16.1
 */

export const UNAVAILABLE = Object.freeze({
  author: {
    reason:
      "Coming soon: publishing a template from one of your agents. It will be checked for company details before anyone can install it.",
    retiredBy: /^\/api\/v1\/(agent-templates\/(author|drafts?|publish)|agents\/\{[^}]+\}\/(template|publish-template))\b/,
  },
  withdraw: {
    reason: "Coming soon: withdrawing a published version so it can no longer be installed. Agents already installed keep running.",
    retiredBy: /^\/api\/v1\/agent-templates\/\{[^}]+\}\/versions\/\{[^}]+\}\/(withdraw|withdrawal|retire)\b/,
  },
});

export const ACT_LABELS = Object.freeze({
  author: "Publish from an agent",
  withdraw: "Withdraw version",
  install: "Install",
  open: "Open",
});

/** Where a template came from, as a person reads it. */
export const ORIGIN_WORDS: Readonly<Record<string, string>> = Object.freeze({
  built_in: "Ships with the product",
  published: "Published on this install",
});

export function originWords(origin: string): string {
  return ORIGIN_WORDS[origin] ?? origin;
}

/** A rung and a model size as a person reads them, as the agent pages spell them. */
export const RUNG_WORDS: Readonly<Record<string, string>> = Object.freeze({
  shadow: "Shadow: it only practises",
  assisted: "Assisted: a person approves each action",
  autonomous: "Autonomous: it acts on its own",
});

export function rungWords(rung: string): string {
  return RUNG_WORDS[rung] ?? rung;
}
