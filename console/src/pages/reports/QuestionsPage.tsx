/**
 * Questions and gaps: what people asked that no connected source could answer, where, and what
 * would fix it.
 *
 * **What an install records is narrower than the design's card**: a question whose shape matches a
 * rule for a source nothing on the install reads, by the department it was asked in and the source
 * that would have answered (`questionsQuery.ts`' `A_COLUMN_WITH_NO_SOURCE_IS_A_SENTENCE`). The words
 * people typed are not kept, so there is no question column, and "I could not find that" is never
 * counted, because it is said alike when nothing exists and when the asker may not see it.
 *
 * **The figures are sums over the lines this reader was sent**, and a line whose source the reader
 * is not told counts in the questions and never as a source, so no figure is about a line or a
 * source they were not shown. A reader who may not be told that nothing is connected is sent the
 * body of a connected install, and the page draws the two alike.
 *
 * What was removed from the old page: six notes under the table (what is recorded, why the words
 * are not kept, why the not-found sentence is never a gap, where usage is, why there was no export,
 * and the window's raw instant). Export is offered now, of the lines drawn.
 *
 * Task ids: M27.7.18, M27.16.1
 */

import { Plug } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { EmptyState, EntityTable, FailureState, KpiStrip, LoadingState, SectionCard, StatCard, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { countWords } from "../agents/agentStats";
import {
  CONNECTORS_PATH,
  askedByDepartment,
  gapFigures,
  questionsApiPathFor,
  readQuestions,
  type GapLineBody,
  type QuestionsBody,
} from "../questionsQuery";
import { BarList, DEFAULT_PERIOD, Quiet, REPORTS_CRUMB, ReportHeader, counted, periodWords, sheetOf, type ReportPeriod } from "./reportParts";

export const QUESTIONS_HEADING = "Questions and gaps";
export const QUESTIONS_LEDE = "What people asked that no connected source could answer, and what would fix it.";
export const QUESTIONS_CRUMBS = [REPORTS_CRUMB, { label: QUESTIONS_HEADING }];

export const LOADING_GAPS = "Loading the unanswered questions.";
export const NO_GAPS = "No gaps to show";
export const NO_GAPS_MORE = "Questions no connected source could answer appear here.";

export const FIGURES_LABEL = "Gap figures";
export const UNANSWERED_LABEL = "Unanswered questions";
export const DEPARTMENTS_LABEL = "Departments asking";
export const SOURCES_LABEL = "Sources to connect";

export const NOTHING_CONNECTED = "Nothing is connected yet";
export const EVERY_ASKER_IS_TOLD = "Every question is answered with:";
export const CONNECT_A_SOURCE = "Connect a source";

export const BY_DEPARTMENT = "Unanswered, by department";
export const BY_DEPARTMENT_LEDE = "Questions that matched a source this install does not read.";
export const NO_GAP_IN_PERIOD = "No unanswered question in this period.";
export const GAPS_HEADING = "What would have answered them";
export const SOURCE_NOT_NAMED = "A source you are not shown";

export const COLUMNS: readonly EntityColumn<GapLineBody>[] = [
  { id: "department", header: "Department", hideable: false, cell: (row) => row.department, text: (row) => row.department },
  { id: "source", header: "Source that would have answered", cell: (row) => row.source ?? SOURCE_NOT_NAMED, text: (row) => row.source ?? SOURCE_NOT_NAMED },
  { id: "asked", header: "Asked", align: "end", cell: (row) => countWords(row.asked), text: (row) => String(row.asked) },
  {
    id: "fix",
    header: "Fix",
    cell: () => (
      <Link to={CONNECTORS_PATH} className="text-acc-text underline-offset-4 hover:underline">
        {CONNECT_A_SOURCE}
      </Link>
    ),
  },
];

function NothingConnected({ body }: { readonly body: QuestionsBody }) {
  return (
    <SectionCard
      title={NOTHING_CONNECTED}
      action={
        <Button asChild size="sm" variant="outline" className="min-h-11 sm:min-h-8">
          <Link to={CONNECTORS_PATH}>
            <Plug aria-hidden /> {CONNECT_A_SOURCE}
          </Link>
        </Button>
      }
    >
      <p className="m-0 text-[13px] text-ink [overflow-wrap:anywhere]">
        <span className="text-dim">{EVERY_ASKER_IS_TOLD}</span> “{body.answered_when_nothing_connected}”
      </p>
    </SectionCard>
  );
}

function Gaps({ body }: { readonly body: QuestionsBody }) {
  const figures = gapFigures(body.gaps);
  const departments = askedByDepartment(body.gaps);
  return (
    <>
      <KpiStrip label={FIGURES_LABEL} count={3}>
        <StatCard label={UNANSWERED_LABEL} value={countWords(figures.asked)} />
        <StatCard label={DEPARTMENTS_LABEL} value={countWords(figures.departments)} />
        <StatCard label={SOURCES_LABEL} value={countWords(figures.sources)} />
      </KpiStrip>
      {body.nothing_connected ? <NothingConnected body={body} /> : null}
      <SectionCard title={BY_DEPARTMENT} lede={BY_DEPARTMENT_LEDE}>
        {departments.length === 0 ? (
          <Quiet>{NO_GAP_IN_PERIOD}</Quiet>
        ) : (
          <BarList
            caption={BY_DEPARTMENT}
            keyHeading="Department"
            valueHeading="Unanswered questions"
            bars={departments.map((one) => ({
              key: one.department,
              label: one.department,
              value: one.asked,
              figure: counted(one.asked, "question", "questions"),
            }))}
          />
        )}
      </SectionCard>
      {body.gaps.length === 0 ? null : (
        <SectionCard title={GAPS_HEADING}>
          <EntityTable
            caption={GAPS_HEADING}
            columns={COLUMNS}
            rows={[...body.gaps].sort((a, b) => b.asked - a.asked)}
            rowId={(row) => `${row.department}|${row.source ?? ""}`}
            rowLabel={(row) => row.department}
          />
        </SectionCard>
      )}
    </>
  );
}

export function QuestionsPage() {
  const [period, setPeriod] = useState<ReportPeriod>(DEFAULT_PERIOD);
  const answer = useResource<unknown>(questionsApiPathFor(period));
  const body = answer.data === null ? null : readQuestions(answer.data);

  let content;
  if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (answer.busy) {
    content = <LoadingState label={LOADING_GAPS} />;
  } else if (body === null) {
    content = <EmptyState title={NO_GAPS} description={NO_GAPS_MORE} />;
  } else {
    content = <Gaps body={body} />;
  }

  const drawn = body !== null && !answer.busy && answer.failure === null && body.gaps.length > 0;
  return (
    <div data-slot="report-page" className="flex min-w-0 flex-col gap-4">
      <ReportHeader
        crumbs={QUESTIONS_CRUMBS}
        title={QUESTIONS_HEADING}
        lede={`${QUESTIONS_LEDE} ${periodWords(period)}.`}
        period={period}
        onPeriod={setPeriod}
        sheets={
          drawn && body !== null
            ? [
                sheetOf(
                  "Unanswered questions",
                  `unanswered-questions-${String(period)}-days`,
                  COLUMNS.filter((one) => one.text !== undefined).map((one) => ({ header: one.header, text: one.text ?? (() => "") })),
                  body.gaps,
                ),
              ]
            : []
        }
      />
      {content}
    </div>
  );
}
