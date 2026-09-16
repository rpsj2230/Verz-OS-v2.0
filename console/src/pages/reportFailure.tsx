/**
 * The two ways a Report screen's request can fail to be answered, said as two sentences.
 *
 * `docs/admin-console.md` asks every screen to tell loading, empty, unreachable and failed apart,
 * and the last two are the pair a page most often collapses: a laptop that has lost its network
 * and an API that answered with a fault both reach a page as a failure. They need different
 * actions from different people, so they get different headings. The difference is read off the
 * one field that carries it, `status`, which `api/errors.transportFailure` sets to zero for a
 * request that never reached the API and which every answer from the API sets to its own code.
 *
 * **Nothing here reads `outcome` or chooses wording from a status the API sent.** A 404 is
 * DENIED or ABSENT and is shown as the API worded it, under the same heading as any other fault,
 * which is `api/errors.A_404_IS_NOT_AN_EXPLANATION`. The only distinction drawn is whether the API
 * was reached at all, and that is a fact about the network rather than about anybody's grants.
 *
 * Shared by the Usage, Questions and Quality screens, which is why it sits beside them rather
 * than inside one of them.
 *
 * Task ids: M27.7.14, M27.7.18, M27.7.19
 */

import type { ApiFailure } from "../api/errors";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

/** The heading when the request never reached the API. */
export const COULD_NOT_REACH_THE_BRAIN = "The Brain could not be reached";

/** Whether a failure is the network's rather than the API's. */
export function neverReachedTheApi(failure: ApiFailure): boolean {
  return failure.status === 0;
}

/** A failed request, under the heading that says which of the two failures it was. */
export function FailureNotice({ failure }: { readonly failure: ApiFailure }) {
  return (
    <Notice
      title={neverReachedTheApi(failure) ? COULD_NOT_REACH_THE_BRAIN : SOMETHING_DID_NOT_WORK}
      traceId={failure.traceId}
    >
      <p>{failure.message}</p>
    </Notice>
  );
}
