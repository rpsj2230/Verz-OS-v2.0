/**
 * The About view of one skill: what it is for, and everything that has happened to it.
 *
 * **What it is for is the newest version's own description**, the line an agent reads to decide when
 * to use it, and never a sentence this page composes.
 *
 * **The history is the audit ledger's** (`skillDetailQuery.readHistory`): every version added,
 * edited, decided, categorised, retired and reinstated, and every assignment and detachment on an
 * agent, newest first, each read through the Activity screen's own route so an entry this reader may
 * not see is not here either. A reader the Activity screen does not open for is told the history is
 * kept there; the failure of any other kind is the API's own sentence.
 *
 * Task ids: M27.16.1, M27.15.55
 */

import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { readLedgerPage } from "../auditQuery";
import { WORKS_AT } from "./skillActions";
import { dayWords, headlineVersion, historyApiPaths, readHistory, type SkillDetail } from "./skillDetailQuery";

export const ABOUT_HEADING = "What it is for";
export const HISTORY_HEADING = "History";
export const LOADING_HISTORY = "Loading this skill's history.";
export const NO_HISTORY = "Nothing is recorded about this skill that you can see.";
export const HISTORY_ELSEWHERE =
  "the history of a skill is read from the activity log, which your account cannot open.";

export function SkillAbout({ detail, profileAddress }: { readonly detail: SkillDetail; readonly profileAddress: string }) {
  const [ownPath, assignedPath] = historyApiPaths(detail.name);
  const own = useResource<unknown>(ownPath);
  const assigned = useResource<unknown>(assignedPath);
  const headline = headlineVersion(detail);
  const failure = own.failure ?? assigned.failure;
  let history;
  if (failure !== null) {
    history =
      failure.status === 404 ? <Note kind="not-yet">{HISTORY_ELSEWHERE}</Note> : <FailureState failure={failure} />;
  } else if (own.busy || assigned.busy) {
    history = <LoadingState label={LOADING_HISTORY} rows={3} />;
  } else {
    const lines = readHistory(readLedgerPage(own.data).rows, readLedgerPage(assigned.data).rows, detail);
    history =
      lines.length === 0 ? (
        <p className="m-0 text-[13px] text-dim">{NO_HISTORY}</p>
      ) : (
        <ol className="m-0 flex list-none flex-col gap-0 p-0">
          {lines.map((line, index) => (
            <li
              key={`${String(index)} ${line.at}`}
              className="[display:grid] grid-cols-1 gap-0.5 border-b border-line py-2 text-[13px] last:border-b-0 sm:grid-cols-[8rem_minmax(0,1fr)] sm:gap-3"
            >
              <span className="font-mono text-[11.5px] text-dim">{dayWords(line.at)}</span>
              <span className="text-ink [overflow-wrap:anywhere]">
                {line.words}
                {line.by === undefined ? null : <span className="text-dim"> by {line.by}</span>}
              </span>
            </li>
          ))}
        </ol>
      );
  }

  return (
    <div data-slot="skill-about" className="flex min-w-0 flex-col gap-4">
      <SectionCard
        title={ABOUT_HEADING}
        lede="The description an agent reads to decide when to use it."
        action={
          <Link to={profileAddress} className="inline-flex items-center gap-1 text-[12px] text-acc-text underline-offset-4 hover:underline">
            See every version <ArrowUpRight aria-hidden className="size-3" />
          </Link>
        }
      >
        <p className="m-0 text-[15px] leading-relaxed font-medium text-ink [overflow-wrap:anywhere]">
          {headline?.description ?? "No version of this skill is in the library you can see."}
        </p>
      </SectionCard>
      <SectionCard
        title={HISTORY_HEADING}
        lede="Every change to it and every agent it was given to or taken off, newest first."
        action={
          <Link to={WORKS_AT.audit} className="inline-flex items-center gap-1 text-[12px] text-acc-text underline-offset-4 hover:underline">
            Activity log <ArrowUpRight aria-hidden className="size-3" />
          </Link>
        }
      >
        {history}
      </SectionCard>
    </div>
  );
}
