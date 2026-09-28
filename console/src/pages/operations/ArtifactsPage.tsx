/**
 * Artifacts, on the page kit: what the system produced, when, what kind, and until when it is kept.
 *
 * `docs/screens.html` draws artifacts as SCREEN 13's "Artifacts it produced" card inside an agent's
 * page; this is that card across every agent this reader may see, under Knowledge and data.
 *
 * **A process with no record of what was produced says so, in the API's words.** An empty table
 * under this heading reads as an estate that produced nothing, so the unread answer is a sentence
 * and never an empty list.
 *
 * **The list is answered whole, so the search, kind and order act on the rows this page holds**, and
 * the toolbar says so. The answer is the whole estate this reader may see, never a page of it, so a
 * narrowing here narrows everything they were sent and nothing else.
 *
 * **Identifiers are columns a reader turns on.** The artifact, the run, the agent and the person it
 * was made for are identifiers the API sends without names; they are hidden until chosen, which is
 * this list's Advanced.
 *
 * **What was removed.** The breadcrumb as text, the identifiers as the rows' names, and the paragraph
 * about downloads (one line now).
 *
 * Task ids: M27.7.23, M27.16.1
 */

import { useId, useState } from "react";
import { useResource } from "../../api/useResource";
import { EmptyState, EntityTable, SectionCard, type EntityColumn } from "../../components/kit";
import { Input } from "../../components/ui/input";
import {
  ARTIFACTS_API_PATH,
  keptUntil,
  narrowed,
  NO_ARTIFACT_FILTERS,
  offeredKinds,
  ORDER_LABELS,
  ORDERS,
  readArtifacts,
  wasRead,
  type ArtifactFilters,
  type ArtifactRow,
  type ArtifactsView,
  type Order,
} from "../artifactsQuery";
import { at, jobName, KNOWLEDGE, Line, OpsPage } from "./parts";
import { Pill } from "./pills";

export const ARTIFACTS_HEADING = "Artifacts";
export const ARTIFACTS_LEDE = "What the system produced: documents, decks, reports, exports and images, and until when each is kept.";
export const READING_ARTIFACTS = "Loading what was produced.";
export const NOTHING_RECORDED = "Nothing on this install records what was produced";
export const NO_ARTIFACTS = "No artifacts yet";
export const NO_ARTIFACTS_MORE = "An artifact appears here once an agent produces one for somebody you may see.";
export const NONE_MATCH = "No artifact matches";
export const NARROWS_THIS_PAGE = "Search, kind and order work on the artifacts listed here.";
export const CARRIES_ITS_RUN =
  "An artifact carries the access of the run that made it, so it cannot be shared wider than its contents allow. Downloads are not offered here.";
export const ARTIFACTS_CAPTION = "Artifacts";
export const FILTERS_LABEL = "Narrow the artifacts";
export const EVERY_KIND = "Every kind";
export const KEPT_RULE_HEADING = "How long an artifact is kept";

const SELECT =
  "h-11 min-w-0 max-w-full rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring sm:h-8";

const COLUMNS: readonly EntityColumn<ArtifactRow>[] = [
  {
    id: "artifact",
    header: "Artifact",
    hideable: false,
    cell: (row) => (
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="font-medium text-ink">{jobName(row.kind)}</span>
        {row.state === "current" ? null : <Pill>{jobName(row.state)}</Pill>}
      </span>
    ),
    text: (row) => row.kind,
  },
  { id: "when", header: "Produced", cell: (row) => at(row.produced_at), text: (row) => row.produced_at },
  { id: "kept", header: "Kept until", cell: (row) => keptUntil(row), text: (row) => keptUntil(row) },
  { id: "class", header: "Kept as", hidden: true, cell: (row) => row.kept_as, text: (row) => row.kept_as },
  { id: "for", header: "For", hidden: true, cell: (row) => row.produced_for, text: (row) => row.produced_for },
  { id: "agent", header: "Agent", hidden: true, cell: (row) => `${row.agent_id} (version ${row.agent_version})`, text: (row) => row.agent_id },
  { id: "reference", header: "Reference", hidden: true, cell: (row) => row.artifact_id, text: (row) => row.artifact_id },
  { id: "run", header: "Run", hidden: true, cell: (row) => row.run_id, text: (row) => row.run_id },
];

function Toolbar({ rows, filters, onChange }: { readonly rows: readonly ArtifactRow[]; readonly filters: ArtifactFilters; readonly onChange: (next: ArtifactFilters) => void }) {
  const searchId = useId();
  const kindId = useId();
  const orderId = useId();
  return (
    <form
      aria-label={FILTERS_LABEL}
      className="flex min-w-0 flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <label htmlFor={searchId} className="sr-only">
        Search
      </label>
      <Input
        id={searchId}
        type="search"
        placeholder="Search artifacts"
        className="h-11 w-full min-w-0 sm:h-8 sm:w-56"
        value={filters.search}
        onChange={(event) => {
          onChange({ ...filters, search: event.target.value });
        }}
      />
      <span className="flex items-center gap-1.5">
        <label htmlFor={kindId} className="text-[12.5px] text-dim">
          Kind
        </label>
        <select
          id={kindId}
          className={SELECT}
          value={filters.kind}
          onChange={(event) => {
            onChange({ ...filters, kind: event.target.value });
          }}
        >
          <option value="">{EVERY_KIND}</option>
          {offeredKinds(rows).map((one) => (
            <option key={one} value={one}>
              {jobName(one)}
            </option>
          ))}
        </select>
      </span>
      <span className="flex items-center gap-1.5">
        <label htmlFor={orderId} className="text-[12.5px] text-dim">
          Order
        </label>
        <select
          id={orderId}
          className={SELECT}
          value={filters.order}
          onChange={(event) => {
            onChange({ ...filters, order: event.target.value as Order });
          }}
        >
          {ORDERS.map((one) => (
            <option key={one} value={one}>
              {ORDER_LABELS[one]}
            </option>
          ))}
        </select>
      </span>
    </form>
  );
}

function Listed({ rows }: { readonly rows: readonly ArtifactRow[] }) {
  const [filters, setFilters] = useState<ArtifactFilters>(NO_ARTIFACT_FILTERS);
  const shown = narrowed(rows, filters);
  if (rows.length === 0) {
    return <EmptyState title={NO_ARTIFACTS} description={NO_ARTIFACTS_MORE} />;
  }
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <Toolbar rows={rows} filters={filters} onChange={setFilters} />
      <Line>{NARROWS_THIS_PAGE}</Line>
      {shown.length === 0 ? (
        <EmptyState title={NONE_MATCH} description="Change the search or the kind." />
      ) : (
        <EntityTable
          caption={ARTIFACTS_CAPTION}
          columns={COLUMNS}
          rows={shown}
          rowId={(row) => row.artifact_id}
          rowLabel={(row) => jobName(row.kind)}
          exportName="artifacts"
        />
      )}
    </div>
  );
}

export function ArtifactsPage() {
  const answer = useResource<ArtifactsView>(ARTIFACTS_API_PATH);
  return (
    <OpsPage
      crumbs={[{ label: KNOWLEDGE }, { label: ARTIFACTS_HEADING }]}
      title={ARTIFACTS_HEADING}
      lede={ARTIFACTS_LEDE}
      loading={READING_ARTIFACTS}
      busy={answer.busy}
      failure={answer.failure}
      body={answer.data}
    >
      {(page) => {
        const read = readArtifacts(page);
        return (
          <>
            <SectionCard title={ARTIFACTS_HEADING} footer={<Line>{CARRIES_ITS_RUN}</Line>}>
              {wasRead(read) ? (
                <Listed rows={read.panel} />
              ) : (
                <div className="flex flex-col gap-1">
                  <p className="m-0 text-sm font-medium text-ink">{NOTHING_RECORDED}</p>
                  <Line>{read.unread}</Line>
                </div>
              )}
            </SectionCard>
            <SectionCard title={KEPT_RULE_HEADING}>
              <p className="m-0 text-sm text-ink">{page.kept_rule}</p>
            </SectionCard>
          </>
        );
      }}
    </OpsPage>
  );
}
