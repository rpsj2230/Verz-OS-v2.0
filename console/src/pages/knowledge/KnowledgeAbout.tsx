/**
 * A document's About: its versions, and what happened to it and when, from the ledger.
 *
 * **The versions are the history the detail route sent**, each one the reader's own place admits,
 * with a link to its own page. **What happened is the history route's**, one line per ledger entry
 * about a version the reader may see: added, verified, handed over, replaced, made company-wide. No
 * line names who did it, and a verification is listed only to a reader the badge would tell its
 * verifier (`brain.knowledge.lifecycle.A_HISTORY_SAYS_WHAT_HAPPENED_AND_WHEN_AND_NEVER_WHO`).
 *
 * Task ids: M27.15.40, M7.4.5
 */

import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { EmptyState, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { dayWords, documentAddress, eventWords, historyPath, readHistory, type VersionRow } from "./knowledgeDocuments";
import { StatePill } from "./parts";

export const VERSIONS_HEADING = "Versions";
export const HISTORY_HEADING = "What happened";
export const LOADING_HISTORY = "Loading what happened.";
export const NO_HISTORY = "Nothing recorded yet";
export const NO_HISTORY_DESCRIPTION = "Each addition, verification, hand-over and replacement is listed here once it happens.";

export function KnowledgeAbout({
  itemId,
  versions,
  version,
}: {
  readonly itemId: string;
  readonly versions: readonly VersionRow[];
  /** Moved after an act on the document, so the history is asked again. */
  readonly version: number;
}) {
  const answer = useResource<unknown>(historyPath(itemId), version);
  const titles = new Map(versions.map((one) => [one.itemId, one.title]));

  let history;
  if (answer.failure !== null) {
    history = <FailureState failure={answer.failure} />;
  } else if (answer.busy) {
    history = <LoadingState label={LOADING_HISTORY} rows={3} />;
  } else {
    const { events, truncated } = readHistory(answer.data);
    history =
      events.length === 0 ? (
        <EmptyState title={NO_HISTORY} description={NO_HISTORY_DESCRIPTION} />
      ) : (
        <>
          <ol className="m-0 flex list-none flex-col p-0">
            {events.map((one, index) => (
              <li
                key={`${String(index)}-${one.itemId}-${one.event}`}
                className="[display:grid] grid-cols-1 gap-0.5 border-b border-line py-2 text-[13px] last:border-b-0 sm:grid-cols-[8rem_minmax(0,1fr)] sm:gap-3"
              >
                <span className="text-dim">{dayWords(one.at) ?? ""}</span>
                <span className="min-w-0 text-ink [overflow-wrap:anywhere]">
                  {eventWords(one.event)}
                  {versions.length > 1 ? <span className="text-dim"> · {titles.get(one.itemId) ?? "an earlier version"}</span> : null}
                </span>
              </li>
            ))}
          </ol>
          {truncated ? <Note>Only the first part of a long history is shown.</Note> : null}
        </>
      );
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title={VERSIONS_HEADING}>
        <ol className="m-0 flex list-none flex-col p-0">
          {versions.map((one) => (
            <li key={one.itemId} className="flex min-w-0 flex-wrap items-center gap-2 border-b border-line py-2 text-[13px] last:border-b-0">
              {one.itemId === itemId ? (
                <span className="font-medium text-ink [overflow-wrap:anywhere]">{one.title}</span>
              ) : (
                <Link to={documentAddress(one.itemId)} className="text-acc-text underline-offset-4 [overflow-wrap:anywhere] hover:underline">
                  {one.title}
                </Link>
              )}
              <StatePill state={one.state} />
              <span className="text-dim">added {dayWords(one.addedAt) ?? "on a day not recorded"}</span>
            </li>
          ))}
        </ol>
      </SectionCard>
      <SectionCard title={HISTORY_HEADING}>{history}</SectionCard>
    </div>
  );
}
