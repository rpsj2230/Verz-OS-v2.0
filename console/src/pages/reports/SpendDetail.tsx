/**
 * The Spend report's other three readings, under its breakdown: what one answer costs, the question
 * shapes that cost most, and the budgets that are stopped (M21.3.3, M21.3.4, M21.3.6).
 *
 * **Every figure is the API's.** The distribution's mean and quantiles, the ranking and the stop
 * list are drawn as sent, never added up or sorted here beyond the order the API gave, and a
 * quantile the sample could not support is absent from the answer and so absent from the page,
 * not drawn as nought. A window with no answer in it says so and draws no figure.
 *
 * **A stop says whether it stopped anything.** A budget recorded while enforcement is off is the
 * install saying what it would have done, and the page words it that way, because a list that read
 * every row as a refusal would send somebody looking for questions that were answered.
 *
 * **Each card fails on its own.** A reading the API cannot give leaves a sentence in its card and
 * the rest of the page as it was.
 *
 * Task ids: M21.3.3, M21.3.4, M21.3.6
 */

import { useResource } from "../../api/useResource";
import { SectionCard } from "../../components/kit";
import { moneyWords, spendDetailPath, type CostPerAnswerBody, type SpendShapesBody, type SpendStopsBody } from "../spendQuery";
import { Quiet } from "./reportParts";

export const ANSWER_COST_HEADING = "What one answer costs";
export const SHAPES_HEADING = "Question shapes that cost most";
export const STOPS_HEADING = "Budgets that are stopped";
export const NO_ANSWERS = "No answer in this period, so there is no figure.";
export const NO_SHAPES = "No cost in this period to rank.";
export const NO_STOPS = "No budget is stopped.";
export const NOT_READ = "This could not be read just now.";
export const STOP_ENFORCED = "questions refused until it ends";
export const STOP_WOULD_HAVE = "said only: the install did not stop anything";

/** A quantile as the words a reader uses for it. */
export function quantileWords(quantile: number): string {
  const percent = Math.round(quantile * 100);
  return percent === 50 ? "Median" : `${String(percent)}th percentile`;
}

function AnswerCost({ days, currency }: { readonly days: number; readonly currency: string }) {
  const answer = useResource<CostPerAnswerBody>(spendDetailPath("cost-per-answer", days));
  return (
    <SectionCard title={ANSWER_COST_HEADING}>
      {answer.failure !== null ? (
        <Quiet>{NOT_READ}</Quiet>
      ) : answer.data === null ? null : answer.data.answers === 0 || answer.data.mean_minor === null ? (
        <Quiet>{NO_ANSWERS}</Quiet>
      ) : (
        <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]">
          <dt className="text-dim">Answers</dt>
          <dd className="m-0">{answer.data.answers.toLocaleString("en-GB")}</dd>
          <dt className="text-dim">Mean</dt>
          <dd className="m-0">{moneyWords(Math.round(answer.data.mean_minor), currency)}</dd>
          {answer.data.quantiles.map((one) => (
            <div key={one.quantile} className="contents">
              <dt className="text-dim">{quantileWords(one.quantile)}</dt>
              <dd className="m-0">{moneyWords(one.cost_minor, currency)}</dd>
            </div>
          ))}
        </dl>
      )}
    </SectionCard>
  );
}

function Shapes({ days, currency }: { readonly days: number; readonly currency: string }) {
  const answer = useResource<SpendShapesBody>(spendDetailPath("shapes", days));
  return (
    <SectionCard title={SHAPES_HEADING}>
      {answer.failure !== null ? (
        <Quiet>{NOT_READ}</Quiet>
      ) : answer.data === null ? null : answer.data.dearest.length === 0 ? (
        <Quiet>{NO_SHAPES}</Quiet>
      ) : (
        <ol className="m-0 flex list-none flex-col gap-1 p-0 text-[13px]">
          {answer.data.dearest.map((one) => (
            <li key={one.shape} className="flex justify-between gap-4">
              <span>{one.shape}</span>
              <span>{moneyWords(one.cost_minor, currency)}</span>
            </li>
          ))}
        </ol>
      )}
    </SectionCard>
  );
}

function Stops() {
  const answer = useResource<SpendStopsBody>(spendDetailPath("stops", null));
  return (
    <SectionCard title={STOPS_HEADING}>
      {answer.failure !== null ? (
        <Quiet>{NOT_READ}</Quiet>
      ) : answer.data === null ? null : answer.data.stops.length === 0 ? (
        <Quiet>{NO_STOPS}</Quiet>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[13px]">
          {answer.data.stops.map((one) => (
            <li key={`${one.level}:${one.subject}:${one.period}:${one.until}`}>
              {`${one.level} ${one.subject}, ${one.period} budget, ${one.enforced ? STOP_ENFORCED : STOP_WOULD_HAVE}`}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

/** The three readings. The stops stand on their own; the other two are cost, so only where it is recorded. */
export function SpendDetail({ days, currency, recorded }: { readonly days: number; readonly currency: string; readonly recorded: boolean }) {
  return (
    <>
      {recorded ? <AnswerCost days={days} currency={currency} /> : null}
      {recorded ? <Shapes days={days} currency={currency} /> : null}
      <Stops />
    </>
  );
}
