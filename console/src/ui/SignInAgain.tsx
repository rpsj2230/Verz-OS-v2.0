/**
 * The one control that sends a person to sign in again so the identity provider asks for their
 * second factor.
 *
 * Drawn in two places, which is why it is one component: under a failure whose body said
 * `second_factor_needed`, by `ui/FailureNotice.tsx`, and in the shell's banner when `GET /me` says
 * the same thing before anything has failed, by `layout/SignInStrength.tsx`. Two buttons with the
 * same words doing two different things would be the worst of both.
 *
 * **It starts a fresh sign-in with `prompt=login` and does not sign out first.** Signing out ends
 * the identity provider's session and lands on the signed-out page, one press further from where
 * the person was working. `beginSignIn` with `forceLogin` keeps the page's address as the place to
 * return to and asks the provider to authenticate again rather than answer from the session that
 * had no second factor: see `auth/session.A_STRONGER_SIGN_IN_HAS_TO_ASK_AGAIN`. Rejected: an
 * ordinary `beginSignIn`, which that same session answers at once, so the button would appear to
 * do nothing at all.
 *
 * **The attempt counter is cleared first**, as `auth/RequireSession.tsx`'s "Try again" clears it: a
 * person pressing a button is not a redirect loop, and a counter left at two from the sign-in that
 * brought them here would stop the one they asked for.
 *
 * Task ids: M27.9.2
 */

import { clearSignInAttempts } from "../auth/pkce";
import { beginSignIn } from "../auth/session";

/** The button's words. */
export const SIGN_IN_AGAIN_WITH_YOUR_AUTHENTICATOR = "Sign in again with your authenticator";

export function SignInAgain() {
  return (
    <button
      type="button"
      className="button"
      onClick={() => {
        clearSignInAttempts();
        void beginSignIn(undefined, { forceLogin: true });
      }}
    >
      {SIGN_IN_AGAIN_WITH_YOUR_AUTHENTICATOR}
    </button>
  );
}
