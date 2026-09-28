/**
 * The About view of one automation: how an automation works, in three sentences, and everything
 * that has happened to this one, newest first.
 *
 * **The history is the install, every start and stop from its agent's page, every pause the runner
 * made and why, and every change from this module**, each with who made it by name. A person the
 * directory no longer holds is named as such rather than by an identifier.
 *
 * Task ids: M27.12.3, M27.15.37, M39.6.1.5
 */

import { Fact, FactList, Note, SectionCard } from "../../components/kit";
import { dateWords, type AutomationDetail } from "./automationsQuery";

export const HOW_HEADING = "How it works";
export const HISTORY_HEADING = "History";
export const NO_HISTORY = "Nothing has happened to it yet.";

/** Three sentences, and no more: what an administrator needs to decide about one. */
export const HOW_IT_WORKS: readonly string[] = [
  "It runs on its schedule as the person it runs as, and can read only what that person may read through its agent.",
  "If that person leaves it stops and waits until somebody adopts it; an adopted automation runs as the adopter once somebody else resumes it.",
  "Pausing and removing take effect before its next run. A removal is final, and its runs and history stay here.",
];

export function AutomationAbout({ detail }: { readonly detail: AutomationDetail }) {
  return (
    <div data-slot="automation-about" className="flex min-w-0 flex-col gap-4">
      <SectionCard title={HOW_HEADING}>
        <ul className="m-0 flex list-disc flex-col gap-1.5 pl-5 text-[13px] text-body">
          {HOW_IT_WORKS.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard title={HISTORY_HEADING}>
        {detail.history.length === 0 ? (
          <Note>{NO_HISTORY}</Note>
        ) : (
          <FactList>
            {detail.history.map((one) => (
              <Fact key={`${one.at} ${one.what}`} label={dateWords(one.at) ?? ""}>
                {one.what}
                {one.byName === "" ? null : <span className="text-dim"> by {one.byName}</span>}
              </Fact>
            ))}
          </FactList>
        )}
      </SectionCard>
    </div>
  );
}
