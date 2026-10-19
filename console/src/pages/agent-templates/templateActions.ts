/**
 * What can be done with a template from its pages, and for each act either where it works or the
 * sentence saying why it cannot be pressed.
 *
 * **Measured against the routes on this branch.** Reading the catalogue and one template, and
 * installing a published version as a new agent (`brain.agent_lifecycle_routes`), are served and
 * live. Withdrawing a published version, putting it back, saving it as a document and bringing
 * one in are live since `brain.template_withdrawal_routes` (M27.15.35), drawn by
 * `TemplateTransfer.tsx`, and their "coming soon" sentence went with the route. Authoring a template
 * from an agent through the leak scan has no route: `brain.agents.authoring` holds the scan and
 * nothing calls it over HTTP. It is an `UNAVAILABLE` sentence, and `tests/agent-templates.test.tsx`
 * reads every `retiredBy` against the API document so the sentence goes when the route arrives.
 *
 * Task ids: M27.11.7, M27.16.1, M27.15.35
 */

export const UNAVAILABLE = Object.freeze({
  author: {
    reason:
      "Coming soon: publishing a template from one of your agents. It will be checked for company details before anyone can install it.",
    retiredBy: /^\/api\/v1\/(agent-templates\/(author|drafts?|publish)|agents\/\{[^}]+\}\/(template|publish-template))\b/,
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
