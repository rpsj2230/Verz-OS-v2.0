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
 * **The list pages on the server, and the search, kind and order are the route's** (M32.5.2.1). Each
 * is a parameter of the request and the rows drawn are the answer to it, so a search finds artifacts
 * the first page did not hold, and "Show more" asks for the page after the last one drawn. They acted
 * on the rows the page held, over one whole answer, until 2026-10-14, which narrows only what arrived
 * and says nothing about the rest. There is no total and no "page 3 of 9": the pager says only
 * whether there is more.
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

import { FETCHING_MORE, NOTHING_MATCHES, SHOW_MORE } from "../../components/ListControls";
import { EmptyState, EntityTable, FailureState, ListToolbar, LoadingState, PageHeader, RESET_LABEL, SectionCard, type EntityColumn } from "../../components/kit";
import { narrows, NO_QUESTION } from "../../components/listing";
import { Button } from "../../components/ui/button";
import { useListing } from "../../components/useListing";
import {
  ARTIFACT_FILTERS,
  ARTIFACT_SORTS,
  ARTIFACTS_API_PATH,
  keptUntil,
  readArtifacts,
  wasRead,
  type ArtifactRow,
  type ArtifactsView,
} from "../artifactsQuery";
import { at, jobName, KNOWLEDGE, Line } from "./parts";
import { Pill } from "./pills";

export const ARTIFACTS_HEADING = "Artifacts";
export const ARTIFACTS_LEDE = "What the system produced: documents, decks, reports, exports and images, and until when each is kept.";
export const READING_ARTIFACTS = "Loading what was produced.";
export const NOTHING_RECORDED = "Nothing on this install records what was produced";
export const NO_ARTIFACTS = "No artifacts yet";
export const NO_ARTIFACTS_MORE = "An artifact appears here once an agent produces one for somebody you may see.";
export const NONE_MATCH = "No artifact matches";
export const CARRIES_ITS_RUN =
  "An artifact carries the access of the run that made it, so it cannot be shared wider than its contents allow. Downloads are not offered here.";
export const ARTIFACTS_CAPTION = "Artifacts";
export const FILTERS_LABEL = "Narrow the artifacts";
export const KEPT_RULE_HEADING = "How long an artifact is kept";

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

function MoreRows({ listing }: { readonly listing: ReturnType<typeof useListing<ArtifactRow>> }) {
  return (
    <div className="flex flex-wrap items-center gap-2 empty:hidden">
      {listing.moreFailure === null ? null : <FailureState failure={listing.moreFailure} />}
      {listing.fetchingMore ? (
        <p role="status" className="m-0 text-[12.5px] text-dim">
          {FETCHING_MORE}
        </p>
      ) : null}
      {listing.more ? (
        <Button
          variant="outline"
          className="min-h-11 sm:min-h-9"
          disabled={listing.fetchingMore}
          onClick={() => {
            listing.showMore();
          }}
        >
          {SHOW_MORE}
        </Button>
      ) : null}
    </div>
  );
}

export function ArtifactsPage() {
  const listing = useListing<ArtifactRow>(ARTIFACTS_API_PATH, { listKey: "artifacts", choices: ARTIFACT_FILTERS });
  const page = listing.body as ArtifactsView | null;
  const read = readArtifacts(page);
  // The answer to the first question is in, and it says nothing records an artifact.
  const nothingRecords = listing.failure === null && !listing.busy && page !== null && !wasRead(read);

  let list;
  if (listing.failure !== null) {
    list = <FailureState failure={listing.failure} />;
  } else if (listing.busy) {
    list = <LoadingState label={READING_ARTIFACTS} />;
  } else if (listing.rows.length === 0) {
    list = narrows(listing.question) ? (
      <EmptyState
        title={NOTHING_MATCHES}
        description="Change the search or clear a filter."
        action={
          <Button
            variant="outline"
            onClick={() => {
              listing.ask({ ...NO_QUESTION, sort: listing.question.sort });
            }}
          >
            {RESET_LABEL}
          </Button>
        }
      />
    ) : (
      <EmptyState title={NO_ARTIFACTS} description={NO_ARTIFACTS_MORE} />
    );
  } else {
    list = (
      <EntityTable
        caption={ARTIFACTS_CAPTION}
        columns={COLUMNS}
        rows={listing.rows}
        rowId={(row) => row.artifact_id}
        rowLabel={(row) => jobName(row.kind)}
        exportName="artifacts"
      />
    );
  }

  return (
    <div data-slot="ops-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: KNOWLEDGE }, { label: ARTIFACTS_HEADING }]} title={ARTIFACTS_HEADING} lede={ARTIFACTS_LEDE} />
      <SectionCard title={ARTIFACTS_HEADING} footer={<Line>{CARRIES_ITS_RUN}</Line>}>
        {nothingRecords ? (
          <div className="flex flex-col gap-1">
            <p className="m-0 text-sm font-medium text-ink">{NOTHING_RECORDED}</p>
            <Line>{read.unread}</Line>
          </div>
        ) : (
          <div className="flex min-w-0 flex-col gap-3">
            <ListToolbar label={FILTERS_LABEL} listing={listing} choices={ARTIFACT_FILTERS} sorts={ARTIFACT_SORTS} searchHint="Search artifacts" />
            {list}
            <MoreRows listing={listing} />
          </div>
        )}
      </SectionCard>
      {page === null || listing.failure !== null ? null : (
        <SectionCard title={KEPT_RULE_HEADING}>
          <p className="m-0 text-sm text-ink">{page.kept_rule}</p>
        </SectionCard>
      )}
    </div>
  );
}
