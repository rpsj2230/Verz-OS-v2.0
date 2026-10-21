/**
 * What is connected for each department, and what to connect next: the Adoption page's coverage
 * section (M34.1.2.1, M34.1.2.2, M34.1.2.3).
 *
 * **Every department the reader's usage grant admits has a line, one with nothing connected
 * included.** A not-connected line says so, in the API's words and not as a nought, because a nought
 * says the system looked and found nothing when it never looked. See
 * `adoptionCoverageQuery.A_NOT_CONNECTED_DEPARTMENT_IS_A_LINE_AND_NOT_A_GAP`.
 *
 * **There is no progress bar and no total.** The shopping list is things a champion can do, in the
 * order the API sent them, and the lines are drawn in the order they arrived; nothing here counts,
 * sums or compares them. A source the reader may not be told of arrives under a label that names
 * none, and is drawn exactly like any other.
 *
 * **Nothing is drawn while the install has the statement switched off**, and no sentence says it is
 * off: the Adoption page is the usage figures alone, as before.
 *
 * Task ids: M34.1.2.1, M34.1.2.2, M34.1.2.3
 */

import { useResource } from "../../api/useResource";
import { EmptyList, EntityTable, FailureState, LoadingState, SectionCard, type EntityColumn } from "../../components/kit";
import { countWords } from "../agents/agentStats";
import { dateWords } from "../connectors/connectorSources";
import { COVERAGE_API_PATH, NOT_READ_YET, NOTHING_TO_SUGGEST, readCoverage, type CoverageRow } from "../adoptionCoverageQuery";
import { Quiet } from "./reportParts";

export const COVERAGE_HEADING = "What is connected for each department";
export const COVERAGE_LEDE = "The sources read for a department, how many records they hold and when they were last read.";
export const COVERAGE_LIST_LABEL = "Coverage by department";
export const LOADING_COVERAGE = "Loading coverage.";
export const NO_COVERAGE = "No coverage to show";
export const NO_COVERAGE_MORE = "A department appears here once it is in the directory and you may read its usage.";
export const SHOPPING_HEADING = "What to do next";
export const SHOPPING_LEDE = "Things a champion can do, with the one whose questions went unanswered most first.";
export const NOTHING_TO_DO = "Every department shown has a source read for it.";

/** Where the source is when the line names none. */
function sourceWords(row: CoverageRow): string {
  return row.sourceLabel ?? row.source ?? NOTHING_TO_SUGGEST;
}

/** The records cell: the count when the API sent one, and a sentence about it when it did not. */
function recordsWords(row: CoverageRow): string {
  if (row.state === "not_connected") {
    return "";
  }
  return row.records === undefined ? NOT_READ_YET : (countWords(row.records) ?? NOT_READ_YET);
}

export const COLUMNS: readonly EntityColumn<CoverageRow>[] = [
  { id: "department", header: "Department", hideable: false, cell: (row) => row.department, text: (row) => row.department },
  { id: "source", header: "Source", cell: (row) => sourceWords(row), text: (row) => sourceWords(row) },
  { id: "state", header: "State", cell: (row) => row.stateWords, text: (row) => row.stateWords },
  { id: "records", header: "Records", align: "end", cell: (row) => recordsWords(row), text: (row) => recordsWords(row) },
  {
    id: "last",
    header: "Last read",
    cell: (row) => dateWords(row.lastSync) ?? "",
    text: (row) => dateWords(row.lastSync) ?? "",
  },
];

export function AdoptionCoverage() {
  const answer = useResource<unknown>(COVERAGE_API_PATH);
  if (answer.busy) {
    return (
      <SectionCard title={COVERAGE_HEADING}>
        <LoadingState label={LOADING_COVERAGE} />
      </SectionCard>
    );
  }
  if (answer.failure !== null) {
    return (
      <SectionCard title={COVERAGE_HEADING}>
        <FailureState failure={answer.failure} />
      </SectionCard>
    );
  }
  const coverage = readCoverage(answer.data);
  if (coverage === null || !coverage.switchedOn) {
    return null;
  }
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title={COVERAGE_HEADING} lede={COVERAGE_LEDE}>
        <div className="flex min-w-0 flex-col gap-3">
          {coverage.rows.length === 0 ? (
            <EmptyList
              title={NO_COVERAGE}
              description={NO_COVERAGE_MORE}
              adds="Found a department on the Departments screen, and it is listed here once you may read its usage."
              by={["super_admin"]}
            />
          ) : (
            <EntityTable
              caption={COVERAGE_LIST_LABEL}
              columns={COLUMNS}
              rows={coverage.rows}
              rowId={(row) => `${row.department}/${row.source ?? ""}`}
              rowLabel={(row) => `${row.department} ${sourceWords(row)}`}
            />
          )}
          {coverage.note === "" ? null : <Quiet>{coverage.note}</Quiet>}
        </div>
      </SectionCard>
      {coverage.rows.length === 0 ? null : (
        <SectionCard title={SHOPPING_HEADING} lede={SHOPPING_LEDE}>
          {coverage.actions.length === 0 ? (
            <Quiet>{NOTHING_TO_DO}</Quiet>
          ) : (
            <ul aria-label={SHOPPING_HEADING} className="m-0 flex list-none flex-col gap-2 p-0">
              {coverage.actions.map((one) => (
                <li key={`${one.department}/${one.source}`} className="min-w-0 text-[13px]">
                  <span className="font-medium">{one.department}</span>: {one.words} ({one.sourceLabel})
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      )}
    </div>
  );
}
