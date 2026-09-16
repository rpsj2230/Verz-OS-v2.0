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
 * **Nothing here reads `outcome` or chooses wording from a status the API sent.** A 404 is DENIED
 * or ABSENT and is shown as the API worded it, under the same heading as any other fault, which is
 * `api/errors.A_404_IS_NOT_AN_EXPLANATION`. The only distinction drawn is whether the API was
 * reached at all, and that is a fact about the network rather than about anybody's grants.
 *
 * Task ids: M27.8.3
 */

import type { ApiFailure } from "../api/errors";
import { Notice } from "./Notice";

/** The heading over a failure the API answered. Its own sentence goes underneath. */
export const THAT_DID_NOT_WORK = "That did not work";

/** The heading when the request never reached the API. */
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

/** Whether a failure is the network's rather than the API's. */
export function neverReachedTheApi(failure: ApiFailure): boolean {
  return failure.status === 0;
}

/** A failed request, under the heading that says which of the two failures it was. */
export function FailureNotice({ failure }: { readonly failure: ApiFailure }) {
  return (
    <Notice
      title={neverReachedTheApi(failure) ? THE_BRAIN_COULD_NOT_BE_REACHED : THAT_DID_NOT_WORK}
      traceId={failure.traceId}
    >
      <p>{failure.message}</p>
    </Notice>
  );
}
