/**
 * Drafts: the reader's own drafts of agents with where each stands, and the publishes waiting for
 * them to approve as the second person.
 *
 * **Two lists and no totals.** `GET /api/v1/agent-drafts` answers the reader's own drafts and the
 * waiting publishes they could approve, each already filtered by the API, and this page draws what
 * arrived in the order it arrived. The waiting list is absent, not empty under a heading, for a
 * reader nothing waits on, because a heading over nothing would say there are publishes they may not
 * see. See `brain.console.scoped_authority.approvable`.
 *
 * **States are words**: a draft, checked, waiting for a second approver, sent back, or published,
 * read off the draft's latest version by the API (`brain.builder.agent_drafts.state_of`).
 *
 * Task ids: M27.11.6, M27.15.31, M27.16.1
 */

import { FilePlus2, FileStack } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  EmptyState,
  EntityTable,
  FailureState,
  LoadingState,
  PageHeader,
  SectionCard,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { ROSTER_HEADING } from "./AgentsPage";
import {
  DRAFTS_API_PATH,
  NEW_AGENT_ADDRESS,
  draftAddress,
  kindWords,
  readDrafts,
  stateWords,
  type DraftSummary,
} from "./agentDraftsQuery";

export const DRAFTS_HEADING = "Drafts";
export const DRAFTS_LEDE = "Agents being written or changed. Nothing in a draft is live until it is published.";
export const YOURS_HEADING = "Your drafts";
export const WAITING_HEADING = "Waiting for you to approve";
export const WAITING_LEDE =
  "Each reaches further than before, so it needs a second person who is not its author. Open one to see what it adds.";
export const NO_DRAFTS = "No drafts yet";
export const NO_DRAFTS_DESCRIPTION =
  "A draft appears here when you start a new agent, or edit an agent as a draft from its page. Anybody who may make agents can start one.";
export const LOADING_DRAFTS = "Loading drafts.";
export const NEW_AGENT_LABEL = "New agent";

function when(value: string | undefined): string {
  return value === undefined
    ? ""
    : new Date(value).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

const COLUMNS: readonly EntityColumn<DraftSummary>[] = [
  {
    id: "name",
    header: "Agent",
    hideable: false,
    cell: (row) => (
      <Link to={draftAddress(row.draftId)} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
        {row.name}
      </Link>
    ),
    text: (row) => row.name,
  },
  { id: "kind", header: "Kind", cell: (row) => kindWords(row.kind), text: (row) => kindWords(row.kind) },
  {
    id: "state",
    header: "State",
    cell: (row) => (
      <span data-slot="draft-state" className="inline-block rounded-[2px] bg-sunk px-1.5 py-0.5 font-mono text-[10.5px] text-ink">
        {stateWords(row.state)}
      </span>
    ),
    text: (row) => stateWords(row.state),
  },
  { id: "saved", header: "Last saved", cell: (row) => when(row.savedAt), text: (row) => when(row.savedAt) },
];

export function DraftsPage() {
  const answer = useResource<unknown>(DRAFTS_API_PATH);
  const drafts = useMemo(() => readDrafts(answer.data), [answer.data]);
  return (
    <div data-slot="drafts-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: ROSTER_HEADING, to: "/agents" }, { label: DRAFTS_HEADING }]}
        title={DRAFTS_HEADING}
        lede={DRAFTS_LEDE}
        primary={
          <Button asChild size="sm" className="min-h-11 no-underline sm:min-h-8">
            <Link to={NEW_AGENT_ADDRESS}>
              <FilePlus2 aria-hidden />
              {NEW_AGENT_LABEL}
            </Link>
          </Button>
        }
      />
      {answer.failure !== null ? (
        <FailureState failure={answer.failure} />
      ) : answer.busy ? (
        <LoadingState label={LOADING_DRAFTS} />
      ) : (
        <>
          {drafts.waitingForYou.length === 0 ? null : (
            <SectionCard title={WAITING_HEADING} lede={WAITING_LEDE}>
              <EntityTable
                caption={WAITING_HEADING}
                columns={COLUMNS}
                rows={drafts.waitingForYou}
                rowId={(row) => row.draftId}
                rowLabel={(row) => row.name}
              />
            </SectionCard>
          )}
          <SectionCard title={YOURS_HEADING}>
            {drafts.items.length === 0 ? (
              <EmptyState title={NO_DRAFTS} description={NO_DRAFTS_DESCRIPTION} icon={<FileStack aria-hidden />} />
            ) : (
              <EntityTable
                caption={YOURS_HEADING}
                columns={COLUMNS}
                rows={drafts.items}
                rowId={(row) => row.draftId}
                rowLabel={(row) => row.name}
              />
            )}
          </SectionCard>
        </>
      )}
    </div>
  );
}
