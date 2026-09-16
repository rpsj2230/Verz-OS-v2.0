/**
 * The capability catalogue: everything that can be granted at all, and what each one reaches.
 *
 * **Whole, or nothing, and never narrowed to what the reader holds.**
 * `brain.console.govern.catalogue` decides that and says why the narrowing is the attractive
 * mistake: showing somebody the capabilities they themselves hold, under a heading reading
 * everything that can be granted, discloses nothing and tells them the vocabulary is smaller
 * than it is. This page therefore has no filter box, no search and no grouping by what the
 * reader holds, and none of those is an omission: a control that narrowed this list on the
 * client would produce exactly the misreading the API refuses to produce on the server.
 *
 * **An empty catalogue is not a refusal and is not rendered as one.** A reader without the
 * grant is answered an empty list rather than a 404, which is that module's decision:
 * `navigation` has already left the screen out of their menu, and a lock drawn on a screen
 * they cannot open is a lock nobody sees. So the empty sentence here is one sentence, true for
 * every reason the list could be empty, exactly as the agent roster's is.
 *
 * **There is no count and no pager.** The route answers the vocabulary whole or refuses to
 * answer it at all, so there is nothing to page through and nothing a number could describe
 * that the list does not already show.
 *
 * Imported statically rather than split, for `Roles`' reason: neither heavy library and no
 * stylesheet of its own.
 *
 * Task ids: M27.7.6
 */

import { useResource } from "../api/useResource";
import { CAPABILITIES_API_PATH, readCapabilities } from "./governQuery";
import { FailureNotice } from "../ui/FailureNotice";

export const CAPABILITIES_HEADING = "Capabilities";

/** Under the heading. Says what the list is and what reading it is for. */
export const CAPABILITIES_LEDE =
  "Everything that can be granted at all, and what each one reaches. Read this before writing " +
  "a grant, not after wondering why one did nothing.";

/**
 * An empty catalogue, whichever of the reasons it is empty.
 *
 * One sentence for two states on purpose: an install whose registry is empty and a reader who
 * may not be told the vocabulary must produce the same page, because the difference between
 * them is the thing being withheld.
 */
export const NO_CAPABILITIES = "There are no capabilities to show.";

/** The accessible name of the list. */
export const CAPABILITIES_LIST_LABEL = "Every capability that can be granted";

function CapabilitiesAnswerView() {
  const answer = useResource<unknown>(CAPABILITIES_API_PATH);

  if (answer.failure) {
    return (
      <FailureNotice failure={answer.failure} />
    );
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }

  const capabilities = readCapabilities(answer.data);
  if (capabilities.length === 0) {
    return <p className="note">{NO_CAPABILITIES}</p>;
  }

  return (
    <dl className="fields" aria-label={CAPABILITIES_LIST_LABEL}>
      {capabilities.map((one) => (
        <div className="fields__row" key={one.capability}>
          <dt>
            <code>{one.capability}</code>
          </dt>
          <dd>{one.description}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Capabilities() {
  return (
    <article className="page">
      <h1>{CAPABILITIES_HEADING}</h1>
      <p className="lede">{CAPABILITIES_LEDE}</p>
      <CapabilitiesAnswerView />
    </article>
  );
}
