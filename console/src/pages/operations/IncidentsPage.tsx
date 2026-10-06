/**
 * Incidents, on the page kit: every connected source that is slow or not answering now, since when,
 * and which tools stop working because of it.
 *
 * **The list is the reader's own.** A source the reader may not be told exists never reaches this
 * page: the route narrows by the Connectors screen's rule, so an empty list here and an install with
 * nothing degraded are the same page, and neither carries a count of anything left out.
 *
 * **A process that looked at nothing says so.** When the API could not read what the worker last
 * found, it sends a sentence in place of the list, and the page draws that sentence rather than
 * "Nothing is degraded".
 *
 * Task ids: M27.2.7
 */

import { useResource } from "../../api/useResource";
import { Note, type EntityColumn } from "../../components/kit";
import { blocksWords, INCIDENTS_API_PATH, INCIDENTS_LABEL, readIncidents, stateWords, type IncidentRow } from "../incidentsQuery";
import { at, Line, OPERATIONS, OpsPage, WholeList } from "./parts";
import { Pill } from "./pills";

export const INCIDENTS_LEDE = "Which connected sources are slow or not answering now, and what stops working because of it.";
export const READING_INCIDENTS = "Loading what is degraded.";
export const NOTHING_DEGRADED = "Nothing is degraded";
export const NOTHING_DEGRADED_MORE =
  "Every source you may see was answering when the worker last read it. A source nobody finished setting up is on the Connectors screen.";
export const DEGRADED_HEADING = "Degraded now";

const COLUMNS: readonly EntityColumn<IncidentRow>[] = [
  { id: "source", header: "Source", hideable: false, cell: (row) => row.subject, text: (row) => row.subject },
  {
    id: "state",
    header: "State",
    cell: (row) => <Pill>{stateWords(row.state)}</Pill>,
    text: (row) => stateWords(row.state),
  },
  { id: "since", header: "Since", cell: (row) => at(row.since), text: (row) => at(row.since) },
  { id: "blocks", header: "What stops working", cell: (row) => blocksWords(row), text: (row) => blocksWords(row) },
];

export function IncidentsPage() {
  const answer = useResource<unknown>(INCIDENTS_API_PATH);
  const body = answer.data === null ? null : readIncidents(answer.data);
  return (
    <OpsPage
      crumbs={[{ label: OPERATIONS }, { label: INCIDENTS_LABEL }]}
      title={INCIDENTS_LABEL}
      lede={INCIDENTS_LEDE}
      loading={READING_INCIDENTS}
      busy={answer.busy}
      failure={answer.failure}
      body={body}
    >
      {(page) =>
        (page.unread ?? "") !== "" ? (
          <Note>{page.unread}</Note>
        ) : (
          <WholeList
            title={DEGRADED_HEADING}
            caption={DEGRADED_HEADING}
            columns={COLUMNS}
            rows={page.items}
            rowId={(row) => row.subject}
            rowLabel={(row) => row.subject}
            exportName="incidents"
            empty={NOTHING_DEGRADED}
            emptyDescription={NOTHING_DEGRADED_MORE}
            footer={<Line>{page.told}</Line>}
          />
        )
      }
    </OpsPage>
  );
}
