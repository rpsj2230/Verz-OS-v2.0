/**
 * A request that was not answered, under the heading that says which of the two ways it failed.
 *
 * `docs/admin-console.md` asks every screen to tell loading, empty, unreachable and failed apart,
 * and the last two are the pair a page most often collapses: a laptop that has lost its network
 * and an API that answered with a fault both reach a page as a failure. They need different
 * actions from different people, so they get different headings. The difference is read off the
 * one field that carries it, `status`, which `api/errors.transportFailure` sets to zero for a
 * request that never reached the API and which every answer from the API sets to its own code.
 *
 * **Written once, here, because it had been written thirty ways.** Until 2026-09-17 the Usage,
 * Questions and Quality screens shared a copy of this in `pages/reportFailure.tsx`, about twenty
 * other pages each carried a private one with the same heading typed out again, and thirty-two
 * addresses drew `That did not work` over both failures. `tests/screen-states.test.tsx` now opens
 * every registered address with its API unreachable and with it failing, and a page drawing the
 * same heading for both fails there.
 *
 * **Every failure carries its reference, or says that none came back.** The same afternoon the
 * owner's staging install showed screen after screen of "That did not work. Something went
 * wrong." with nothing a person could quote, because a dozen pages drew a failure through a copy
 * of this that dropped the trace id, and the rest drew it only when there was one. A failure the
 * API answered always has a reference now, so a failure with none was answered by something in
 * front of the application, and saying so is the one fact an administrator needs to look in the
 * proxy's log rather than the Brain's. `tests/screen-states.test.tsx` holds every registered
 * address to it. See `A_FAILURE_WITHOUT_ITS_REFERENCE_IS_A_DEAD_END`.
 *
 * **What the API refused in the request is listed here when no input on the screen can hold it.**
 * A form passes the names of its inputs as `fields` and draws the rest beside them with
 * `ui/FieldProblems.tsx`; a screen with no form passes nothing, and every problem is listed. See
 * `api/problems.A_PROBLEM_WITH_NO_INPUT_IS_STILL_SAID`.
 *
 * **A sign-in without a second factor is decided by its flag and offers the way out.** When the
 * API says `second_factor_needed`, the heading says so, the API's own message is shown even where
 * a screen would otherwise use its own sentence, and `ui/SignInAgain.tsx` offers a fresh sign-in
 * that makes the identity provider ask again. It is never "I could not find that" and never an
 * empty screen, although the status is the 404 every refusal is. See
 * `api/errors.THE_SECOND_FACTOR_IS_READ_FROM_ITS_FLAG`.
 *
 * **Nothing here reads `outcome` or chooses wording from a status the API sent.** A 404 is DENIED
 * or ABSENT and is shown as the API worded it, under the same heading as any other fault, which is
 * `api/errors.A_404_IS_NOT_AN_EXPLANATION`. The only distinctions drawn are whether the API was
 * reached at all, which is a fact about the network, and whether the API said a second factor is
 * needed, which is a fact about this session and never about anybody's data.
 *
 * Task ids: M27.8.3, M27.8.5
 */

import type { ReactNode } from "react";
import type { ApiFailure } from "../api/errors";
import { unmatchedProblems } from "../api/problems";
import { Notice } from "./Notice";
import { SignInAgain } from "./SignInAgain";

/** The heading over a failure the API answered. Its own sentence goes underneath. */
export const THAT_DID_NOT_WORK = "That did not work";

/** The heading when the request never reached the API. */
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

/** The heading when the API said this sign-in needs a second factor. */
export const A_SECOND_FACTOR_IS_NEEDED = "This needs a sign-in with a second factor";

/** Said where a reference would be, when a failure that reached something came back without one. */
export const NO_REFERENCE_CAME_BACK =
  "No reference came back with this failure, so it was not answered by the Brain itself and the " +
  "Brain's own log will not name it. The log of the proxy in front of the Brain is where to look.";

/** The label of the list of problems that no input on the screen can hold. */
export const WHAT_WAS_NOT_ACCEPTED = "What was not accepted";

/** The rule a page drawing a failure of its own must not break. */
export const A_FAILURE_WITHOUT_ITS_REFERENCE_IS_A_DEAD_END =
  "Every failure a screen draws shows its reference when it has one, and says that none came back " +
  "when it reached something and has none. A failure with neither is a sentence nobody can follow " +
  "up, which is what the staging install showed on every screen.";

/** Whether a failure is the network's rather than the API's. */
export function neverReachedTheApi(failure: ApiFailure): boolean {
  return failure.status === 0;
}

interface FailureNoticeProps {
  readonly failure: ApiFailure;
  /**
   * The heading over a failure the API answered, for a screen that has its own, such as setup's
   * "Setup did not continue". Never used for a failure that did not reach the API, or for one
   * asking for a second factor, which have their own.
   */
  readonly title?: string;
  /**
   * A sentence in place of the API's message: the constant a setup refusal is always drawn as, see
   * `setup/wizard.A_SETUP_REFUSAL_NAMES_NO_REASON`, or the sentence a refusal's own document carried,
   * such as a 409 that says why an automation was not installed. Never used when the API said a
   * second factor is needed, because then the API's message is the only one that says what to do.
   */
  readonly sentence?: string;
  /**
   * Every name the API may use for an input on the form this failure came from. A problem naming
   * one of them is drawn beside that input and not repeated here. Left out on a screen with no
   * form, where every problem is listed.
   */
  readonly fields?: readonly string[];
  /** Anything the screen says after the message, such as what to try next. */
  readonly children?: ReactNode;
}

function headingFor(failure: ApiFailure, title: string | undefined): string {
  if (neverReachedTheApi(failure)) {
    return THE_BRAIN_COULD_NOT_BE_REACHED;
  }
  if (failure.secondFactorNeeded) {
    return A_SECOND_FACTOR_IS_NEEDED;
  }
  return title ?? THAT_DID_NOT_WORK;
}

/** A failed request, under the heading that says which of the failures it was. */
export function FailureNotice({ failure, title, sentence, fields = [], children }: FailureNoticeProps) {
  const unmatched = unmatchedProblems(failure.problems, fields);
  return (
    <Notice
      title={headingFor(failure, title)}
      traceId={failure.traceId}
      {...(neverReachedTheApi(failure) ? {} : { withoutTrace: NO_REFERENCE_CAME_BACK })}
    >
      <p>{failure.secondFactorNeeded || sentence === undefined ? failure.message : sentence}</p>
      {unmatched.length === 0 ? null : (
        <ul className="failure-problems" aria-label={WHAT_WAS_NOT_ACCEPTED}>
          {unmatched.map((one, at) => (
            <li key={`${String(at)} ${one.field}`}>
              {one.field === "" ? null : (
                <>
                  <code>{one.field}</code>{" "}
                </>
              )}
              {one.message}
            </li>
          ))}
        </ul>
      )}
      {children}
      {failure.secondFactorNeeded ? (
        <div className="form-actions">
          <SignInAgain />
        </div>
      ) : null}
    </Notice>
  );
}
