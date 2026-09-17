/**
 * The shell's banner for a sign-in that has no second factor, on every page, before anything fails.
 *
 * `layout/signInStrengthQuery.ts` reads what `GET /me` says; this draws it. **Drawn only when the
 * API's flag is true.** The flag is the API's decision from this session and the person's own
 * grants, so the banner is never inferred here from the assurance word or from a refusal: a person
 * at `strong` gets no banner, and a person at `authenticated` who holds nothing a second factor
 * would restore gets none either, because telling them to sign in again would send them round a loop
 * that changes nothing.
 *
 * **Nothing is drawn while `/me` is on its way, or if it fails.** A banner is advice, and the page
 * under it has its own states. A shell that drew a second failure notice above every page whenever
 * `/me` could not be had would be saying the same thing twice on the one screen that is about it.
 *
 * **Its own request rather than the Overview's.** `api/useResource.ts` does not cache, on purpose,
 * so the Overview and the shell each ask; one extra read of the caller's own facts per page load is
 * cheaper than a shared cache holding facts about whoever was signed in when it filled.
 *
 * Task ids: M27.9.2
 */

import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import { SignInAgain } from "../ui/SignInAgain";
import {
  ADMINISTRATION_NEEDS_A_SECOND_FACTOR,
  ME_API_PATH,
  THIS_SIGN_IN_HAS_NO_SECOND_FACTOR,
  readSignInStrength,
  withheldSentence,
} from "./signInStrengthQuery";

export function SignInStrength() {
  const answer = useResource<unknown>(ME_API_PATH);
  if (answer.data === null) {
    return null;
  }
  const strength = readSignInStrength(answer.data);
  if (!strength.secondFactorNeeded) {
    return null;
  }
  const withheld = withheldSentence(strength.withheldVerbs);
  return (
    <div className="shell__banner">
      <Notice title={THIS_SIGN_IN_HAS_NO_SECOND_FACTOR}>
        <p>{ADMINISTRATION_NEEDS_A_SECOND_FACTOR}</p>
        {withheld === "" ? null : <p>{withheld}</p>}
        <div className="form-actions">
          <SignInAgain />
        </div>
      </Notice>
    </div>
  );
}
