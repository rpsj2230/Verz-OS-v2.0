/**
 * The Connectors list, built on the shared page kit: every source this release ships, whether it
 * is connected here, how reading it is going, the department its records answer to, when it was
 * last read, and how many ids of it this install keeps.
 *
 * **Every source is a row, connected or not.** The list is `GET /api/v1/console/connectors`
 * (`brain.connector_routes.connector_sources`), which is total over the shipped declarations, so a
 * source that could be connected is on the same list as one that is, and a source this reader may
 * not be told is connected reads "Not connected" in the same words. Nothing here decides who is
 * told what; the page draws the rows it was sent, in the order they came, with no count anywhere.
 *
 * **The index size is ids, from the shared stats route, one connected row at a time.** A source
 * that is not connected has no figures and none is asked for. A figure the route did not send reads
 * "Not recorded yet", and a row whose figures failed reads "Not available", never nought.
 *
 * **Connecting, Connect Lark and disconnecting work from here**; editing, replacing a key, the
 * export and testing a connection are on a source's own page, where its settings are and where what
 * a test found is shown.
 *
 * **What was removed from the old screen, and why.** The table's wiring, key, ceiling and projected
 * columns (each is on a source's page now); the principal id beside who connected a source; the
 * sentence about today's calls having no numerator; the paragraph about what connecting starts,
 * which the connect confirmation says in the API's words; the "Tested against recordings" card and
 * the "Connected at the server instead" card, which were a second and a third list of the same
 * sources and are now one row each and a line on the source's About view; and the trust paragraphs
 * repeated under the table for every connection, which are the source's Profile.
 *
 * Task ids: M27.11.9, M11.7.7, M27.16.1, M27.10.2, M27.15.8
 */

import { Cable, MoreHorizontal, Plus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import type { FilterChoice, SortChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { Chip, Fact, FactList, ListPage, NOT_RECORDED, Note, SectionCard, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { Skeleton } from "../../components/ui/skeleton";
import { CONNECTORS_API_PATH, CONNECTORS_LABEL, type Connectors as ConnectorsBody } from "../connectorsQuery";
import { ACT_LABELS } from "./connectorActions";
import {
  CONNECT_FROM_WORDS,
  SOURCES_API_PATH,
  connectorAddress,
  dateWords,
  healthWords,
  readSourceRows,
  statusWords,
  type SourceRow,
} from "./connectorSources";
import { idsWords } from "./connectorStats";
import { DriftPill, HealthPill, StatusPill } from "./pills";
import { ConnectDrawer, DisconnectDialog, LarkDrawer, type OpenAct } from "./SourceActs";
import { useSourceStats, type SourceStats } from "./useSourceStats";

/** The page's heading, which is also the menu's label for it. */
export const CONNECTORS_HEADING = CONNECTORS_LABEL;

/** Under the heading. What the list is, in one sentence. */
export const CONNECTORS_LEDE =
  "Every outside system this product can read. A connection keeps a small index of ids and reads every value live.";

export const LOADING_SOURCES = "Loading sources.";
export const NO_SOURCES = "No sources to show";
export const NO_SOURCES_DESCRIPTION = "Every source this release ships appears here, connected or not.";
export const SOURCES_LIST_LABEL = "Sources";
export const FILTERS_LABEL = "Narrow the sources";
export const SEARCH_HINT = "Search sources";
export const CONNECT_A_SOURCE = "Connect a source";
export const NOT_AVAILABLE = "Not available";
export const NEVER = "Never";
export const WHAT_WE_COPY = "What we copy, and what we never copy";

export const SOURCE_COLUMN = "Source";
export const STATUS_COLUMN = "Status";
export const HEALTH_COLUMN = "Health";
export const DEPARTMENT_COLUMN = "Department";
export const LAST_READ_COLUMN = "Last read";
export const INDEX_COLUMN = "Index";
export const CONNECTED_COLUMN = "Connected";

/** The filters the list route declares that this page offers, over values on rows drawn. */
export const SOURCE_FILTERS: readonly FilterChoice<SourceRow>[] = [
  { column: "status", label: STATUS_COLUMN, everything: "Any status", read: (row) => row.status, describe: statusWords },
  { column: "health", label: HEALTH_COLUMN, everything: "Any health", read: (row) => row.health, describe: healthWords },
  { column: "department", label: DEPARTMENT_COLUMN, everything: "All departments", read: (row) => row.department },
  {
    column: "connect_from",
    label: "Connected from",
    everything: "Anywhere",
    read: (row) => row.connectFrom,
    describe: (value) => CONNECT_FROM_WORDS[value] ?? value,
  },
];

export const SOURCE_SORTS: readonly SortChoice[] = [
  { value: "", label: "Name" },
  { value: "status", label: STATUS_COLUMN },
  { value: "department", label: DEPARTMENT_COLUMN },
  { value: "-last_read_at", label: "Last read, newest first" },
];

/** Whether a row stands for a connection the stats route can describe: one made on this screen. */
export function hasFigures(row: SourceRow): boolean {
  return row.connectedAt !== undefined;
}

function IndexFigure({ stats }: { readonly stats: SourceStats }) {
  if (stats.kind === "loading") {
    return <Skeleton aria-label="Loading" className="h-4 w-16" />;
  }
  if (stats.kind === "failed") {
    return <span className="text-[12px] text-dim">{NOT_AVAILABLE}</span>;
  }
  const value = idsWords(stats.stats.indexIds);
  return value === undefined ? (
    <span className="text-[12px] text-dim">{NOT_RECORDED}</span>
  ) : (
    <span className="font-mono text-[12px] text-ink tabular-nums">{value}</span>
  );
}

function lastReadWords(row: SourceRow): string {
  if (row.lastReadAt !== undefined) {
    return dateWords(row.lastReadAt) ?? "";
  }
  return hasFigures(row) ? NEVER : "";
}

function RowMenu({
  row,
  onAct,
}: {
  readonly row: SourceRow;
  readonly onAct: (act: OpenAct) => void;
}) {
  const connected = row.status !== "not_connected";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.label}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuItem asChild>
          <Link to={connectorAddress(row.name)}>{ACT_LABELS.open}</Link>
        </DropdownMenuItem>
        {row.connectFrom === "console" && row.mayManage && !connected ? (
          <DropdownMenuItem
            onSelect={() => {
              onAct({ act: "connect", source: row.name });
            }}
          >
            {ACT_LABELS.connect}
          </DropdownMenuItem>
        ) : null}
        {row.connectFrom === "lark" ? (
          <DropdownMenuItem
            onSelect={() => {
              onAct({ act: "lark" });
            }}
          >
            {ACT_LABELS.connectLark}
          </DropdownMenuItem>
        ) : null}
        {row.connectFrom === "console" && row.mayManage && hasFigures(row) ? (
          <DropdownMenuItem
            onSelect={() => {
              onAct({ act: "disconnect", source: row.name, label: row.label });
            }}
          >
            {ACT_LABELS.disconnect}
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The copy policy, served whole by the API: what is kept of any source and what never is. */
function CopyPolicy({ page }: { readonly page: ConnectorsBody | null }) {
  if (page === null || page.copy_policy.length === 0) {
    return null;
  }
  return (
    <SectionCard title={WHAT_WE_COPY}>
      <FactList>
        {page.copy_policy.map((line) => (
          <Fact key={line.what} label={line.what}>
            <span className="flex flex-col gap-1">
              <span>
                <Chip>{line.verdict}</Chip>
              </span>
              <span className="text-[12.5px] text-dim">{line.why}</span>
            </span>
          </Fact>
        ))}
      </FactList>
    </SectionCard>
  );
}

export function ConnectorsPage() {
  const [version, setVersion] = useState(0);
  const [open, setOpen] = useState<OpenAct | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const listing = useListing<SourceRow>(SOURCES_API_PATH, { choices: SOURCE_FILTERS, version });
  const rows = useMemo(() => readSourceRows(listing.body), [listing.body]);
  const statsOf = useSourceStats(useMemo(() => rows.filter(hasFigures).map((row) => row.name), [rows]));
  const context = useResource<ConnectorsBody>(CONNECTORS_API_PATH, version);
  const page = context.data;

  const done = useCallback((sentence: string) => {
    setOpen(null);
    setTold(sentence);
    setVersion((count) => count + 1);
  }, []);
  const close = useCallback(() => {
    setOpen(null);
  }, []);
  // Connect Lark says what it did in its own card, so closing it only reads the list again.
  const closeLark = useCallback(() => {
    setOpen(null);
    setVersion((count) => count + 1);
  }, []);

  const columns: readonly EntityColumn<SourceRow>[] = [
    {
      id: "name",
      header: SOURCE_COLUMN,
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[12rem] flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-2">
            <Link to={connectorAddress(row.name)} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
              {row.label}
            </Link>
            {row.declarationChanged ? <DriftPill /> : null}
          </span>
          <span className="text-[12px] text-dim">{CONNECT_FROM_WORDS[row.connectFrom] ?? row.connectFrom}</span>
        </span>
      ),
      text: (row) => row.label,
    },
    {
      id: "status",
      header: STATUS_COLUMN,
      cell: (row) => <StatusPill status={row.status} />,
      text: (row) => statusWords(row.status),
    },
    {
      id: "health",
      header: HEALTH_COLUMN,
      cell: (row) => (row.health === undefined ? null : <HealthPill health={row.health} />),
      text: (row) => (row.health === undefined ? "" : healthWords(row.health)),
    },
    {
      id: "department",
      header: DEPARTMENT_COLUMN,
      cell: (row) => row.department ?? null,
      text: (row) => row.department ?? "",
    },
    {
      id: "last_read",
      header: LAST_READ_COLUMN,
      cell: (row) => <span className="font-mono text-[12px] tabular-nums">{lastReadWords(row)}</span>,
      text: lastReadWords,
    },
    {
      id: "index",
      header: INDEX_COLUMN,
      align: "end",
      cell: (row) => (hasFigures(row) ? <IndexFigure stats={statsOf(row.name)} /> : null),
      text: (row) => {
        const stats = statsOf(row.name);
        return hasFigures(row) && stats.kind === "ready" ? (idsWords(stats.stats.indexIds) ?? "") : "";
      },
    },
    {
      id: "connected",
      header: CONNECTED_COLUMN,
      hidden: true,
      cell: (row) => dateWords(row.connectedAt) ?? null,
      text: (row) => dateWords(row.connectedAt) ?? "",
    },
  ];

  return (
    <>
      <ListPage
        crumbs={[{ label: CONNECTORS_HEADING }]}
        title={CONNECTORS_HEADING}
        lede={CONNECTORS_LEDE}
        primary={
          <Button
            className="min-h-11 sm:min-h-8"
            disabled={page === null}
            onClick={() => {
              setTold(null);
              setOpen({ act: "connect", source: null });
            }}
          >
            <Plus aria-hidden />
            {CONNECT_A_SOURCE}
          </Button>
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            className="min-h-11 sm:min-h-8"
            onClick={() => {
              setTold(null);
              setOpen({ act: "lark" });
            }}
          >
            {ACT_LABELS.connectLark}
          </Button>
        }
        notice={
          <>
            {told === null || told === "" ? null : (
              <div role="status">
                <Note kind="works">{told}</Note>
              </div>
            )}
            {page === null || page.vault_told === "" ? null : <Note kind="not-yet">{page.vault_told}</Note>}
          </>
        }
        listing={listing}
        rows={rows}
        filtersLabel={FILTERS_LABEL}
        choices={SOURCE_FILTERS}
        sorts={SOURCE_SORTS}
        searchHint={SEARCH_HINT}
        caption={SOURCES_LIST_LABEL}
        columns={columns}
        rowId={(row) => row.name}
        rowLabel={(row) => row.label}
        rowActions={(row) => (
          <RowMenu
            row={row}
            onAct={(act) => {
              setTold(null);
              setOpen(act);
            }}
          />
        )}
        exportName="connectors"
        loading={LOADING_SOURCES}
        emptyTitle={NO_SOURCES}
        emptyDescription={NO_SOURCES_DESCRIPTION}
        emptyIcon={<Cable aria-hidden />}
        footer={<CopyPolicy page={page} />}
      />
      {open?.act === "connect" && page !== null ? (
        <ConnectDrawer page={page} source={open.source} onClose={close} onDone={done} />
      ) : null}
      {open?.act === "lark" ? <LarkDrawer onClose={closeLark} /> : null}
      {open?.act === "disconnect" && page !== null ? (
        <DisconnectDialog name={open.source} label={open.label} consequence={page.confirm_disconnect} onClose={close} onDone={done} />
      ) : null}
    </>
  );
}
