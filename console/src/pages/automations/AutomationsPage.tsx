/**
 * The Automations list, built on the shared page kit: every automation this reader may see, with
 * its agent, whom it runs as, its schedule, where it stands, and when it last and next ran.
 *
 * **Every row is one the API sent, in the order it came, with no count anywhere.** The list is
 * `GET /api/v1/console/automations` (`brain.automations_routes.automations`), which is the union over
 * the agents this reader may see of each agent's own automations this reader may see. An automation
 * on an agent the reader cannot see is not on the list and nothing says one was left off.
 *
 * **Adding one happens on its agent's page**, where the gallery of outcomes is, because an
 * automation belongs to an agent and runs as the person who adds it; the primary button goes to the
 * agents list. Pausing, resuming, changing the schedule, removing and adopting are on an
 * automation's own page, where the confirmation can show what will change.
 *
 * Task ids: M27.12.3, M39.6.1.4, M27.16.1, M27.10.2
 */

import { Workflow } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { FilterChoice, SortChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { ListPage, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { ACT_LABELS } from "./automationActions";
import {
  AUTOMATIONS_API_PATH,
  automationAddress,
  dateWords,
  outcomeWords,
  readAutomationRows,
  stateWords,
  type AutomationRow,
} from "./automationsQuery";
import { StatePill } from "./pills";

/** The page's heading, which is also the menu's label for it. */
export const AUTOMATIONS_HEADING = "Automations";

/** Under the heading. What the list is, in one sentence. */
export const AUTOMATIONS_LEDE =
  "What each agent does on a schedule, as the person it runs as. Add one from an agent's page.";

export const LOADING_AUTOMATIONS = "Loading automations.";
export const NO_AUTOMATIONS = "No automations to show";
export const NO_AUTOMATIONS_DESCRIPTION = "An automation added to an agent from its gallery appears here.";
export const AUTOMATIONS_LIST_LABEL = "Automations";
export const FILTERS_LABEL = "Narrow the automations";
export const SEARCH_HINT = "Search automations";
export const NOT_SCHEDULED = "Not scheduled";

export const NAME_COLUMN = "Automation";
export const AGENT_COLUMN = "Agent";
export const OWNER_COLUMN = "Runs as";
export const SCHEDULE_COLUMN = "Schedule";
export const STATE_COLUMN = "State";
export const LAST_RUN_COLUMN = "Last run";
export const NEXT_RUN_COLUMN = "Next run";

/** The filters the list route declares, over values on rows drawn. */
export const AUTOMATION_FILTERS: readonly FilterChoice<AutomationRow>[] = [
  { column: "state", label: STATE_COLUMN, everything: "Any state", read: (row) => row.state, describe: stateWords },
  { column: "agent", label: AGENT_COLUMN, everything: "All agents", read: (row) => row.agentName },
  { column: "owner", label: OWNER_COLUMN, everything: "Anyone", read: (row) => row.ownerName },
];

export const AUTOMATION_SORTS: readonly SortChoice[] = [
  { value: "", label: "Name" },
  { value: "state", label: STATE_COLUMN },
  { value: "agent", label: AGENT_COLUMN },
  { value: "next_run_at", label: "Next run, soonest first" },
  { value: "-last_run_at", label: "Last run, newest first" },
];

function lastRunWords(row: AutomationRow): string {
  if (row.lastRunAt === undefined) {
    return "";
  }
  const at = dateWords(row.lastRunAt) ?? "";
  return row.lastOutcome === undefined ? at : `${outcomeWords(row.lastOutcome)}, ${at}`;
}

function nextRunWords(row: AutomationRow): string {
  return row.nextRunAt === undefined ? NOT_SCHEDULED : (dateWords(row.nextRunAt) ?? "");
}

export function AutomationsPage() {
  const listing = useListing<AutomationRow>(AUTOMATIONS_API_PATH, { choices: AUTOMATION_FILTERS });
  const rows = useMemo(() => readAutomationRows(listing.body), [listing.body]);

  const columns: readonly EntityColumn<AutomationRow>[] = [
    {
      id: "name",
      header: NAME_COLUMN,
      hideable: false,
      cell: (row) => (
        <Link
          to={automationAddress(row.id)}
          className="block min-w-[12rem] font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline"
        >
          {row.name}
        </Link>
      ),
      text: (row) => row.name,
    },
    {
      id: "state",
      header: STATE_COLUMN,
      cell: (row) => <StatePill state={row.state} />,
      text: (row) => stateWords(row.state),
    },
    { id: "agent", header: AGENT_COLUMN, cell: (row) => row.agentName, text: (row) => row.agentName },
    { id: "owner", header: OWNER_COLUMN, cell: (row) => row.ownerName, text: (row) => row.ownerName },
    {
      id: "schedule",
      header: SCHEDULE_COLUMN,
      cell: (row) => row.schedule ?? null,
      text: (row) => row.schedule ?? "",
    },
    {
      id: "last_run",
      header: LAST_RUN_COLUMN,
      cell: (row) => <span className="font-mono text-[12px] tabular-nums">{lastRunWords(row)}</span>,
      text: lastRunWords,
    },
    {
      id: "next_run",
      header: NEXT_RUN_COLUMN,
      cell: (row) => <span className="font-mono text-[12px] tabular-nums">{nextRunWords(row)}</span>,
      text: nextRunWords,
    },
  ];

  return (
    <ListPage
      crumbs={[{ label: AUTOMATIONS_HEADING }]}
      title={AUTOMATIONS_HEADING}
      lede={AUTOMATIONS_LEDE}
      primary={
        <Button asChild className="min-h-11 sm:min-h-8">
          <Link to="/agents">{ACT_LABELS.add}</Link>
        </Button>
      }
      listing={listing}
      rows={rows}
      filtersLabel={FILTERS_LABEL}
      choices={AUTOMATION_FILTERS}
      sorts={AUTOMATION_SORTS}
      searchHint={SEARCH_HINT}
      caption={AUTOMATIONS_LIST_LABEL}
      columns={columns}
      rowId={(row) => row.id}
      rowLabel={(row) => row.name}
      exportName="automations"
      loading={LOADING_AUTOMATIONS}
      emptyTitle={NO_AUTOMATIONS}
      emptyDescription={NO_AUTOMATIONS_DESCRIPTION}
      emptyIcon={<Workflow aria-hidden />}
    />
  );
}
