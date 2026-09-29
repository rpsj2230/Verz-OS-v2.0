/**
 * Elevation requests on the shared page kit: who asked for more access than they hold, what they
 * were given, and when it lapses; ask for more from the header, and decide what others asked for.
 *
 * **One list and one act in the header.** The old screen was four cards: your standing, a form drawn
 * open, the requests and a card of rules. The standing is one line under the heading, the form is a
 * drawer behind Ask for access that says what each field takes, the requests are the list, and the
 * rules are the sentence the confirmation carries, so they are read at the moment they matter.
 *
 * **Nothing here decides who may see or decide a request.** The rows are
 * `brain.console.elevation.requests_shown`'s answer, Approve and Deny are offered only where the API
 * said the row is decidable, and the route asks again whatever this page drew.
 *
 * **The break-glass notices addressed to the reader are listed under the requests (M1.2.5)**, and
 * only when there are some: they are the reader's own, so an empty section would say nothing.
 *
 * Task ids: M27.7.8, M27.8.6, M1.2.5, M27.16.1
 */

import { KeyRound, MoreHorizontal, Plus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { EntityTable, ListPage, Note, SectionCard, type EntityColumn } from "../../components/kit";
import { useListing } from "../../components/useListing";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import {
  BREAK_GLASS_NOTICES_API_PATH,
  ELEVATION_API_PATH,
  ELEVATION_DECISIONS,
  ELEVATION_FILTERS,
  ELEVATION_SORTS,
  readBreakGlassNotices,
  readElevation,
  reasonWords,
  STATE_WORDS,
  type BreakGlassNoticeRow,
  type ElevationDecisionWord,
  type ElevationRequestRow,
} from "../governPeopleQuery";
import { AskDrawer, useElevationDecisions } from "./ElevationActs";
import { LINK, nameOf, peopleIn, whenWords } from "./parts";
import { ElevationPill } from "./pills";
import { ACT_LABELS } from "./reviewActions";
import { hoursWords, requestAddress, REVIEW_CRUMB } from "./reviewQuery";

export const ELEVATION_HEADING = "Elevation requests";
export const READING_ELEVATION = "Reading the elevation requests you may see.";
export const NO_REQUESTS = "No elevation requests";
export const NO_REQUESTS_MORE = "A request appears here when somebody asks for more access than they hold, for a few hours.";
export const REQUESTS_LABEL = "Elevation requests";
export const FILTERS_LABEL = "Narrow the requests";
export const SEARCH_HINT = "Search requests";
export const MORE_REQUESTS = "This list came back full, so there are more requests than it shows. Narrow it to read the rest.";
export const TOLD_HEADING = "Emergency access you were told about";
export const TOLD_LEDE = "Each approved elevation opens a break-glass session, and every standing Super Admin who took no part in it is told.";
export const TOLD_LABEL = "Emergency access you were told about";

function DecideMenu({
  row,
  busy,
  onDecide,
}: {
  readonly row: ElevationRequestRow;
  readonly busy: boolean;
  readonly onDecide: (row: ElevationRequestRow, decision: ElevationDecisionWord) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.capability}, ${nameOf({}, row.principal_id, row.display_name)}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem asChild>
          <Link to={requestAddress(row.request_id)}>{ACT_LABELS.open}</Link>
        </DropdownMenuItem>
        {row.decidable ? <DropdownMenuSeparator /> : null}
        {row.decidable
          ? ELEVATION_DECISIONS.map((decision) => (
              <DropdownMenuItem
                key={decision}
                disabled={busy}
                onSelect={() => {
                  onDecide(row, decision);
                }}
              >
                {decision === "approved" ? ACT_LABELS.approve : ACT_LABELS.deny}
              </DropdownMenuItem>
            ))
          : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ToldAbout({ version }: { readonly version: number }) {
  const answer = useResource<unknown>(BREAK_GLASS_NOTICES_API_PATH, version);
  const told = readBreakGlassNotices(answer.data);
  const people = peopleIn(answer.data);
  if (answer.failure !== null || told.length === 0) {
    return null;
  }
  const columns: readonly EntityColumn<BreakGlassNoticeRow>[] = [
    { id: "who", header: "Who", hideable: false, cell: (one) => nameOf(people, one.principal_id), text: (one) => nameOf(people, one.principal_id) },
    { id: "why", header: "Why", cell: (one) => reasonWords(one.reason), text: (one) => reasonWords(one.reason) },
    { id: "allowed", header: "Allowed by", cell: (one) => nameOf(people, one.authorised_by), text: (one) => nameOf(people, one.authorised_by) },
    { id: "until", header: "Until", cell: (one) => whenWords(one.lapses_at), text: (one) => whenWords(one.lapses_at) },
  ];
  return (
    <SectionCard title={TOLD_HEADING} lede={TOLD_LEDE}>
      <EntityTable caption={TOLD_LABEL} columns={columns} rows={told} rowId={(one) => one.session_id} rowLabel={(one) => nameOf(people, one.principal_id)} />
    </SectionCard>
  );
}

export function ElevationPage() {
  const [version, setVersion] = useState(0);
  const [asking, setAsking] = useState(false);
  const [asked, setAsked] = useState<string | null>(null);
  const onDone = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const listing = useListing<ElevationRequestRow>(ELEVATION_API_PATH, { choices: ELEVATION_FILTERS, version });
  const page = useMemo(() => readElevation(listing.body), [listing.body]);
  const people = useMemo(() => peopleIn(listing.body), [listing.body]);
  const decisions = useElevationDecisions({ what: page?.what ?? "", recorded: page?.recorded ?? "" }, onDone);
  const rows = page?.items ?? [];

  const columns: readonly EntityColumn<ElevationRequestRow>[] = [
    {
      id: "person",
      header: "Person",
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[10rem] flex-col">
          <Link to={requestAddress(row.request_id)} className={LINK}>
            {nameOf(people, row.principal_id, row.display_name)}
          </Link>
          {row.department === null ? null : <span className="text-[12px] text-dim">{row.department}</span>}
        </span>
      ),
      text: (row) => nameOf(people, row.principal_id, row.display_name),
    },
    {
      id: "asked_for",
      header: "Asked for",
      cell: (row) => (
        <span className="flex flex-col">
          <span className="font-mono text-[12px] text-ink [overflow-wrap:anywhere]">{row.capability}</span>
          <span className="text-[12px] text-dim">{`over ${row.scope_slug}, ${hoursWords(row.hours)}`}</span>
        </span>
      ),
      text: (row) => `${row.capability} over ${row.scope_slug}, ${hoursWords(row.hours)}`,
    },
    {
      id: "why",
      header: "Why",
      cell: (row) => reasonWords(row.reason),
      text: (row) => reasonWords(row.reason),
    },
    {
      id: "asked",
      header: "Asked",
      className: "whitespace-nowrap",
      cell: (row) => whenWords(row.requested_at),
      text: (row) => whenWords(row.requested_at),
    },
    {
      id: "state",
      header: "Where it stands",
      cell: (row) => (
        <span className="flex flex-col gap-0.5">
          <span>
            <ElevationPill state={row.state} />
          </span>
          {row.lapses_at === null ? null : <span className="text-[12px] text-dim">{`Lapses ${whenWords(row.lapses_at)}`}</span>}
        </span>
      ),
      text: (row) => STATE_WORDS[row.state],
    },
    {
      id: "decided",
      header: "Decided by",
      cell: (row) => (row.decided_by === null ? null : nameOf(people, row.decided_by)),
      text: (row) => (row.decided_by === null ? "" : nameOf(people, row.decided_by)),
    },
    {
      id: "explanation",
      header: "What it is for",
      hidden: true,
      cell: (row) => row.explanation,
      text: (row) => row.explanation,
    },
  ];

  return (
    <>
      <ListPage
        crumbs={[{ label: REVIEW_CRUMB }, { label: ELEVATION_HEADING }]}
        title={ELEVATION_HEADING}
        lede={page?.prompt}
        primary={
          page === null || page.reasons.length === 0 ? undefined : (
            <Button
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                setAsked(null);
                setAsking(true);
              }}
            >
              <Plus aria-hidden /> {ACT_LABELS.ask}
            </Button>
          )
        }
        notice={
          <>
            {asked === null ? null : (
              <div role="status">
                <Note kind="works">{asked}</Note>
              </div>
            )}
            {decisions.drawn}
          </>
        }
        listing={listing}
        rows={rows}
        filtersLabel={FILTERS_LABEL}
        choices={ELEVATION_FILTERS}
        sorts={ELEVATION_SORTS}
        searchHint={SEARCH_HINT}
        caption={REQUESTS_LABEL}
        columns={columns}
        rowId={(row) => row.request_id}
        rowLabel={(row) => `${row.capability}, ${nameOf(people, row.principal_id, row.display_name)}`}
        rowActions={(row) => <DecideMenu row={row} busy={decisions.busy} onDecide={decisions.decide} />}
        exportName="elevation-requests"
        loading={READING_ELEVATION}
        emptyTitle={NO_REQUESTS}
        emptyDescription={NO_REQUESTS_MORE}
        emptyIcon={<KeyRound aria-hidden />}
        footer={
          <>
            {page?.truncated === true ? <Note>{MORE_REQUESTS}</Note> : null}
            <ToldAbout version={version} />
          </>
        }
      />
      {asking && page !== null ? (
        <AskDrawer
          reasons={page.reasons}
          longest={page.longest_hours}
          what={page.what}
          onClose={() => {
            setAsking(false);
          }}
          onAsked={(sentence) => {
            setAsking(false);
            setAsked(sentence);
            onDone();
          }}
        />
      ) : null}
    </>
  );
}
