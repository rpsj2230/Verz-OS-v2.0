/**
 * What can be done to a channel from the Channels module, and for each act either where it works
 * or, for the one that is not built, its label (the sentence saying why is the server's).
 *
 * **Measured against the routes on this branch.** On 2026-09-29 the API served, for one channel:
 * saving its set-up with a write-only secret (`PUT /channels/{name}`), switching it on or off
 * (`POST /channels/{name}/switch`), a test message (`POST /channels/{name}/test`), the people bound
 * on it and unbinding one (`/channels/{name}/bindings`), and, for a person, a one-time code in My
 * workspace (`POST /me/channels/{name}/code`). It served no route that checks a request signed with
 * the stored secret is accepted: that act is a `kit/Explanation` of the `action` form
 * (`channel.verify`).
 *
 * **Binding somebody else's account is not offered at all**, so it is an `Explanation` of the `line`
 * form (`channel.bind_for_somebody`) and no control: a chat account is bound only by its own person sending a code they asked for while
 * signed in, which is what makes the binding theirs.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/unit/test_console_explanations.py` reads every expiry against the routes the application mounts.
 *
 * Task ids: M27.13.1, M27.16.1
 */

/** The labels of the acts, one spelling each, so a menu and a test agree. */
export const ACT_LABELS = Object.freeze({
  open: "Open",
  setUp: "Edit set-up",
  switchOn: "Switch on",
  switchOff: "Switch off",
  save: "Save set-up",
  test: "Send test message",
  unbind: "Unbind",
  verify: "Check inbound signing",
});
