/**
 * The Report screens' name for the one failure notice, kept so a page importing it still builds.
 *
 * `ui/FailureNotice.tsx` is where the notice is written, once, for every screen. This file held a
 * copy until 2026-09-17 and pages written against it are still arriving, so it now hands over the
 * same component and heading under the names it always had rather than a second implementation.
 * A new page imports from `ui/FailureNotice.tsx`.
 *
 * Task ids: M27.8.3
 */

export {
  FailureNotice,
  neverReachedTheApi,
  THE_BRAIN_COULD_NOT_BE_REACHED as COULD_NOT_REACH_THE_BRAIN,
} from "../ui/FailureNotice";
