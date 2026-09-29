/**
 * The Agents list, built on the shared page kit: every agent this reader may open, with its state,
 * its leash, its steward, when it last ran and how often.
 *
 * **This is the reference module list.** Everything a list page repeats is `kit/ListPage`; what is
 * here is only what is this module's own: the route (`GET /api/v1/agents`), the columns, the
 * filters and orders the route declares (`brain.agent_routes.ROSTER`), the empty sentence, and which
 * acts are live. A module added next month copies this file's shape.
 *
 * **Nothing on this page decides who is listed.** The API filters by audience before it bounds the
 * answer, and the page draws what arrived in the order it arrived, with no count anywhere: see
 * `pages/agentsQuery.ts`' `A_ROSTER_DRAWS_WHAT_IT_WAS_SENT_AND_COUNTS_NOTHING`. The state and the
 * leash columns are filled only for a reader the API sends them to, which is a reader of an agent's
 * Settings tab; for everybody else those cells are empty, never "unknown", because a word there
 * would say something was withheld.
 *
 * **Names, not identifiers.** The steward is their display name; the agent's slug and the steward's
 * principal id are how the system names them and are off this page (they are on the agent's own
 * page, in its Advanced section). The old roster printed both.
 *
 * **The figures come from the stats route, one agent at a time**, and a row whose figures are not
 * there says "Not recorded yet" or "Not available", never nought. See `agentStats.ts`.
 *
 * **Switching on and off, archiving and duplicating are live on each row** for a reader the roster
 * sends a state to, each confirmed through `LifecycleActs.tsx`, which asks the lifecycle route what
 * this reader may do before it confirms anything. New agent opens the guided start
 * (`NewAgentPage.tsx`), and Drafts lists what the reader is building and what waits for them to
 * approve. The one bulk act is export, which reads: agents change one at a time.
 *
 * Imported statically, as the roster always was, because the kit reaches nothing heavier than the
 * shell already does.
 *
 * Task ids: M39.1.2.5, M27.8.6, M27.10.2, M27.11.6
 */

import { Bot, MoreHorizontal, Plus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { FilterChoice, SortChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { AGENT_ADDRESS_PREFIX } from "../../components/agentWorkspaceState";
import { Chip, ListPage, NOT_RECORDED, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { Skeleton } from "../../components/ui/skeleton";
import { scopeLines } from "../scopeText";
import { ROSTER_API_PATH } from "../agentsQuery";
import { actsFor, ACT_LABELS, type LifecycleAct } from "../agentLifecycleQuery";
import { rungWords, stateWords, WORKS_AT } from "./agentActions";
import { DRAFTS_ADDRESS, NEW_AGENT_ADDRESS } from "./agentDraftsQuery";
import { countWords, FIRST_PERIOD, periodOf, whenWords } from "./agentStats";
import { useLifecycleActs } from "./LifecycleActs";
import { LeashPill, StatePill } from "./pills";
import { useRowStats, type RowStats } from "./useRowStats";

/** The page's heading. */
export const ROSTER_HEADING = "Agents";

/** Under the heading. Says what the list is, and nothing about what it is not. */
export const ROSTER_LEDE =
  "Every agent you can open. An agent works for the person using it and never reaches more than they can.";

/** Said while the first page is on its way. */
export const LOADING_AGENTS = "Loading agents.";

/** The empty state, whichever of the reasons it is empty. */
export const NO_AGENTS = "No agents to show";
export const NO_AGENTS_DESCRIPTION =
  "An agent appears here once somebody builds one with New agent and publishes it, and it is offered to you. Administrators who may make agents can start one.";

/** What the table is, for a screen reader. */
export const ROSTER_LIST_LABEL = "Agents you can open";
export const FILTERS_LABEL = "Narrow the agents";
export const SEARCH_HINT = "Search agents";

export const NEW_AGENT = "New agent";
export const DRAFTS_LINK = "Drafts";
export const TEMPLATES_LINK = "Agent templates";

/** A row's figures that could not be read. Never a number. */
export const NOT_AVAILABLE = "Not available";

export const AGENT_COLUMN = "Agent";
export const STATUS_COLUMN = "Status";
export const LEASH_COLUMN = "Leash";
export const OWNER_COLUMN = "Steward";
export const LAST_RUN_COLUMN = "Last run";
export const RUNS_COLUMN = "Runs, 30 days";
export const DEPARTMENT_COLUMN = "Department";
export const CEILING_COLUMN = "Most it may reach";

/** One agent on the list, as the roster route sends it. */
export interface AgentRow {
  readonly agentId: string;
  readonly displayName: string;
  readonly department?: string;
  readonly ownerName?: string;
  readonly state?: string;
  readonly leashUpTo?: string;
  readonly ceiling?: readonly string[];
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

/**
 * The rows out of the roster's body: an entry is carried only with its id and name, once, in the
 * order it came, and every other field only when it was sent. `readRoster`'s rules, for the new
 * fields too.
 */
export function readAgentRows(payload: unknown): readonly AgentRow[] {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return [];
  }
  // A cast at the boundary, where proving a structural match buys nothing: every value is read back
  // through `said` or `scopeLines`.
  const items = (payload as Readonly<Record<string, unknown>>)["items"];
  if (!Array.isArray(items)) {
    return [];
  }
  const seen = new Set<string>();
  const rows: AgentRow[] = [];
  for (const item of items as readonly unknown[]) {
    const entry =
      typeof item === "object" && item !== null && !Array.isArray(item) ? (item as Readonly<Record<string, unknown>>) : undefined;
    const agentId = said(entry?.["agent_id"]);
    const displayName = said(entry?.["display_name"]);
    if (entry === undefined || agentId === undefined || displayName === undefined || seen.has(agentId)) {
      continue;
    }
    seen.add(agentId);
    const department = said(entry["department"]);
    const ownerName = said(entry["owner_name"]);
    const state = said(entry["state"]);
    const leashUpTo = said(entry["leash_up_to"]);
    const ceiling = scopeLines(entry["ceiling"]);
    rows.push({
      agentId,
      displayName,
      ...(department === undefined ? {} : { department }),
      ...(ownerName === undefined ? {} : { ownerName }),
      ...(state === undefined ? {} : { state }),
      ...(leashUpTo === undefined ? {} : { leashUpTo }),
      ...(ceiling.length === 0 ? {} : { ceiling }),
    });
  }
  return rows;
}

/** Where one agent's page is, as `brain.console.workspace.deep_link` spells the prefix. */
export function agentAddress(agentId: string): string {
  return `${AGENT_ADDRESS_PREFIX}${encodeURIComponent(agentId)}`;
}

/** The filters the roster route declares that this page offers, over values on rows drawn. */
export const AGENT_FILTERS: readonly FilterChoice<AgentRow>[] = [
  { column: "state", label: STATUS_COLUMN, everything: "Any status", read: (row) => row.state, describe: stateWords },
  { column: "leash_up_to", label: LEASH_COLUMN, everything: "Any leash", read: (row) => row.leashUpTo, describe: rungWords },
  { column: "department", label: DEPARTMENT_COLUMN, everything: "All departments", read: (row) => row.department },
];

export const AGENT_SORTS: readonly SortChoice[] = [
  { value: "", label: "Name" },
  { value: "department", label: "Department" },
  { value: "owner_name", label: "Steward" },
  { value: "state", label: "Status" },
];

function Figure({ stats, pick }: { readonly stats: RowStats; readonly pick: (stats: RowStats & { kind: "ready" }) => string | undefined }) {
  if (stats.kind === "loading") {
    return <Skeleton aria-label="Loading" className="h-4 w-16" />;
  }
  if (stats.kind === "failed") {
    return <span className="text-[12px] text-dim">{NOT_AVAILABLE}</span>;
  }
  const value = pick(stats);
  return value === undefined ? (
    <span className="text-[12px] text-dim">{NOT_RECORDED}</span>
  ) : (
    <span className="font-mono text-[12px] text-ink tabular-nums">{value}</span>
  );
}

function statsText(stats: RowStats, pick: (stats: RowStats & { kind: "ready" }) => string | undefined): string {
  return stats.kind === "ready" ? (pick(stats) ?? "") : "";
}

function RowMenu({
  row,
  onChoose,
  busy,
}: {
  readonly row: AgentRow;
  readonly onChoose: (agentId: string, act: LifecycleAct) => void;
  readonly busy: boolean;
}) {
  // A lifecycle act is offered only on a row the roster sent a state for, which is a reader of the
  // agent's Settings tab; the lifecycle route then says whether this reader may press it.
  const acts: readonly LifecycleAct[] = row.state === undefined ? [] : ["duplicate", ...actsFor(row.state)];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.displayName}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuItem asChild>
          <Link to={agentAddress(row.agentId)}>Open</Link>
        </DropdownMenuItem>
        {acts.length === 0 ? null : <DropdownMenuSeparator />}
        {acts.map((act) => (
          <DropdownMenuItem
            key={act}
            disabled={busy}
            onSelect={() => {
              onChoose(row.agentId, act);
            }}
          >
            {ACT_LABELS[act]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AgentsPage() {
  // Asked again under a new version after a lifecycle act, so the row shows what the API now holds.
  const [version, setVersion] = useState(0);
  const onChanged = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const lifecycle = useLifecycleActs(onChanged, agentAddress);
  const listing = useListing<AgentRow>(ROSTER_API_PATH, { choices: AGENT_FILTERS, version });
  const rows = useMemo(() => readAgentRows(listing.body), [listing.body]);
  const statsOf = useRowStats(useMemo(() => rows.map((row) => row.agentId), [rows]));

  const columns: readonly EntityColumn<AgentRow>[] = [
    {
      id: "name",
      header: AGENT_COLUMN,
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[12rem] flex-col">
          <Link to={agentAddress(row.agentId)} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
            {row.displayName}
          </Link>
          {row.department === undefined ? null : <span className="text-[12px] text-dim">{row.department}</span>}
        </span>
      ),
      text: (row) => row.displayName,
    },
    {
      id: "state",
      header: STATUS_COLUMN,
      cell: (row) => (row.state === undefined ? null : <StatePill state={row.state} />),
      text: (row) => (row.state === undefined ? "" : stateWords(row.state)),
    },
    {
      id: "leash",
      header: LEASH_COLUMN,
      cell: (row) => (row.leashUpTo === undefined ? null : <LeashPill rung={row.leashUpTo} />),
      text: (row) => (row.leashUpTo === undefined ? "" : rungWords(row.leashUpTo)),
    },
    {
      id: "owner",
      header: OWNER_COLUMN,
      cell: (row) => row.ownerName ?? null,
      text: (row) => row.ownerName ?? "",
    },
    {
      id: "last_run",
      header: LAST_RUN_COLUMN,
      cell: (row) => <Figure stats={statsOf(row.agentId)} pick={(one) => whenWords(one.stats.lastActiveAt)} />,
      text: (row) => statsText(statsOf(row.agentId), (one) => one.stats.lastActiveAt),
    },
    {
      id: "runs",
      header: RUNS_COLUMN,
      align: "end",
      cell: (row) => <Figure stats={statsOf(row.agentId)} pick={(one) => countWords(periodOf(one.stats, FIRST_PERIOD)?.runs)} />,
      text: (row) => statsText(statsOf(row.agentId), (one) => countWords(periodOf(one.stats, FIRST_PERIOD)?.runs)),
    },
    {
      id: "department",
      header: DEPARTMENT_COLUMN,
      hidden: true,
      cell: (row) => row.department ?? null,
      text: (row) => row.department ?? "",
    },
    {
      id: "ceiling",
      header: CEILING_COLUMN,
      hidden: true,
      cell: (row) =>
        row.ceiling === undefined ? null : (
          <span className="flex flex-wrap gap-1">
            {row.ceiling.map((line) => (
              <Chip key={line} mono>
                {line}
              </Chip>
            ))}
          </span>
        ),
      text: (row) => (row.ceiling ?? []).join("; "),
    },
  ];

  return (
    <ListPage
      crumbs={[{ label: ROSTER_HEADING }]}
      title={ROSTER_HEADING}
      lede={ROSTER_LEDE}
      primary={
        <Button asChild size="sm" className="min-h-11 no-underline sm:min-h-8">
          <Link to={NEW_AGENT_ADDRESS}>
            <Plus aria-hidden />
            {NEW_AGENT}
          </Link>
        </Button>
      }
      actions={
        <>
          <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
            <Link to={DRAFTS_ADDRESS}>{DRAFTS_LINK}</Link>
          </Button>
          <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
            <Link to={WORKS_AT.templates}>{TEMPLATES_LINK}</Link>
          </Button>
        </>
      }
      listing={listing}
      rows={rows}
      filtersLabel={FILTERS_LABEL}
      choices={AGENT_FILTERS}
      sorts={AGENT_SORTS}
      searchHint={SEARCH_HINT}
      caption={ROSTER_LIST_LABEL}
      columns={columns}
      rowId={(row) => row.agentId}
      rowLabel={(row) => row.displayName}
      rowActions={(row) => <RowMenu row={row} onChoose={lifecycle.choose} busy={lifecycle.busy} />}
      exportName="agents"
      notice={
        <>
          {lifecycle.notice}
          {lifecycle.dialog}
        </>
      }
      loading={LOADING_AGENTS}
      emptyTitle={NO_AGENTS}
      emptyDescription={NO_AGENTS_DESCRIPTION}
      emptyIcon={<Bot aria-hidden />}
      emptyAction={
        <Button asChild variant="outline" className="text-ink no-underline">
          <Link to={NEW_AGENT_ADDRESS}>{NEW_AGENT}</Link>
        </Button>
      }
    />
  );
}
