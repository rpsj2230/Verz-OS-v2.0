/**
 * A change the matrix gate held, said the way the owner asked on 2026-09-28: why, in one sentence;
 * what failed, by the golden question's own text; and the three steps that get a change through.
 * The raw cases and reasons stay behind Details, for whoever follows one up.
 *
 * **Every change is held until a golden question is answered through it**, and a golden question
 * counts only when the model answers from documents the person it is asked as can read, so a new
 * install cannot change its matrix until it has a document and a question. That rule is the owner's
 * safety rule and is not weakened here; what this adds is the way through, said where the change
 * was made.
 *
 * Task ids: M5.6.2, M5.3.3, M27.16.1
 */

import { Link } from "react-router-dom";
import { Note } from "../../components/kit";
import { KNOWLEDGE_PATH } from "../knowledgeQuery";
import {
  caseReasonWords,
  caseWords,
  DETAILS,
  GOLDEN_COUNTS_WHEN,
  heldSentence,
  heldWhy,
  HOW_TO_PASS,
  needsGoldenSteps,
  STEPS_TO_PASS,
  type ChangeRow,
  type GoldenRow,
} from "../matrixGateQuery";

/** What counts as an answered golden question, and the three steps that get a change through. */
export function StepsToPass() {
  return (
    <div aria-label={HOW_TO_PASS} className="flex flex-col gap-2">
      <Note>{GOLDEN_COUNTS_WHEN}</Note>
      <p className="m-0 text-[13px] font-medium text-ink">{HOW_TO_PASS}</p>
      <ol className="m-0 flex flex-col gap-1.5 pl-5 text-[13px] text-body">
        {STEPS_TO_PASS.map((step, index) => (
          <li key={step}>
            {index === 0 ? (
              <>
                {step}{" "}
                <Link to={KNOWLEDGE_PATH} className="text-acc-text underline-offset-4 hover:underline">
                  Open Knowledge
                </Link>
              </>
            ) : (
              step
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Why a held change was held, what failed, the way through, and the raw record behind Details. */
export function HeldExplanation({
  change,
  golden,
  goldenCount,
}: {
  readonly change: ChangeRow;
  readonly golden: readonly GoldenRow[];
  /** How many golden questions are recorded now, or null where the page does not know. */
  readonly goldenCount: number | null;
}) {
  return (
    <div data-slot="held-change" className="flex flex-col gap-3">
      <p className="m-0 text-[13.5px] text-ink">
        {heldSentence(change)} {heldWhy(change, goldenCount)}
      </p>
      {change.failing.length === 0 ? null : (
        <ul aria-label="What failed" className="m-0 flex flex-col gap-1 pl-5 text-[13px] text-body">
          {change.failing.map((one) => (
            <li key={one.case} className="[overflow-wrap:anywhere]">
              {caseWords(one.case, golden)}: {caseReasonWords(one.reason)}
            </li>
          ))}
        </ul>
      )}
      {needsGoldenSteps(change) ? <StepsToPass /> : null}
      <details className="text-[12.5px] text-dim">
        <summary className="cursor-pointer">{DETAILS}</summary>
        <div className="mt-2 flex flex-col gap-1">
          {change.reasons.map((reason) => (
            <p key={reason} className="m-0 [overflow-wrap:anywhere]">
              {reason}
            </p>
          ))}
          {change.failing.map((one) => (
            <p key={one.case} className="m-0 font-mono text-[11.5px] [overflow-wrap:anywhere]">
              {one.case}: {one.reason}
            </p>
          ))}
        </div>
      </details>
    </div>
  );
}
