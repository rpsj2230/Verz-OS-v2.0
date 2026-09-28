/**
 * What can be done to a channel from the Channels module, and for each act either where it works
 * or the one sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes on this branch.** On 2026-09-29 the API served, for one channel:
 * saving its set-up with a write-only secret (`PUT /channels/{name}`), switching it on or off
 * (`POST /channels/{name}/switch`), a test message (`POST /channels/{name}/test`), the people bound
 * on it and unbinding one (`/channels/{name}/bindings`), and, for a person, a one-time code in My
 * workspace (`POST /me/channels/{name}/code`). It served no route that checks a request signed with
 * the stored secret is accepted: that act is an `UNAVAILABLE` sentence below and is drawn as
 * `kit/UnavailableAction`.
 *
 * **Binding somebody else's account is not offered at all**, so it is a `NOT_OFFERED` sentence and
 * no control: a chat account is bound only by its own person sending a code they asked for while
 * signed in, which is what makes the binding theirs.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/channels-page.test.tsx` reads every `retiredBy` against the API document.
 *
 * Task ids: M27.13.1, M27.16.1
 */

export const UNAVAILABLE = Object.freeze({
  verify: {
    label: "Check inbound signing",
    reason:
      "Coming soon: a check that a request signed with the stored secret is accepted. Until then, a message sent from the chat shows as accepted under History.",
    retiredBy: /^\/api\/v1\/channels\/\{[^}]+\}\/(verify|verification|check)$/,
  },
});

export type UnavailableAct = keyof typeof UNAVAILABLE;

export const NOT_OFFERED = Object.freeze({
  bindForSomebody:
    "People connect their own chat account from My workspace with a one-time code. Nobody binds another person's account.",
});

/** The labels of the acts, one spelling each, so a menu and a test agree. */
export const ACT_LABELS = Object.freeze({
  open: "Open",
  setUp: "Edit set-up",
  switchOn: "Switch on",
  switchOff: "Switch off",
  save: "Save set-up",
  test: "Send test message",
  unbind: "Unbind",
});
