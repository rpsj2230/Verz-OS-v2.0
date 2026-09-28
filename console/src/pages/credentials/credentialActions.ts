/**
 * What can be done to a credential from its pages, and for each act either where it works or the
 * one sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes on main on 2026-09-29.** Setting and replacing a value is
 * `PUT /api/v1/credentials/{family}/{name}` for every slot the install declares, and is live on
 * every slot the list marks writable. A source's first key goes in by connecting it on Connectors,
 * and a provider's key is checked against its provider on Models; both are links, because the act
 * exists and lives there. Checking a source's key with its vendor before the worker's next read has
 * no route, so it is `UNAVAILABLE` and drawn inert, and `tests/credentials-page.test.tsx` reads its
 * `retiredBy` against the API document so the sentence goes the day the route arrives.
 *
 * **Removing a credential is not offered, and that is a product decision, not a gap.** The vault's
 * application policy grants no delete, and a key removed takes everything using it off at once;
 * what an administrator does is replace one. So it is a `NotOffered` sentence, never a control.
 *
 * Task ids: M27.11.10
 */

/** Why each act that has no route cannot be pressed, and the API path whose arrival retires it. */
export const UNAVAILABLE = Object.freeze({
  checkSource: {
    reason: "Coming soon: checking a source's key with its vendor without waiting for the next read.",
    retiredBy: /^\/api\/v1\/connectors\/\{[^}]+\}\/(test|check)$/,
  },
});

/** Said where a Remove control would be. */
export const NOT_REMOVED =
  "A credential is replaced, never removed: removing one would stop everything that uses it at once, " +
  "and the vault gives this system no way to delete one.";

/** Where the acts that live on other pages are done, as console addresses. */
export const WORKS_AT = Object.freeze({
  /** Connecting a source, which writes its first key. */
  connectors: "/connectors",
  /** Checking a provider's key against the provider. */
  models: "/models",
  /** The relay's host, port and sender, and a test message. */
  notifications: "/notifications",
  /** The vault's run-token leases and audit shipping. */
  vault: "/vault",
});
