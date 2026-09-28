/**
 * The Channels list, built on the shared page kit: every chat channel this release declares that
 * the reader manages, whether it is set up and switched on, whether its secret is held, how its
 * deliveries say it is doing, how many people are bound on it and when it was last active.
 *
 * **Every declared channel is a row, set up or not.** The list is `GET /api/v1/console/channels`
 * (`brain.binding_routes.channel_list`) on the server list contract, so a channel nobody set up is
 * on the same list as one that runs, searched, filtered and ordered on the server. A channel the
 * reader may not manage is no row, and nothing here counts what is not drawn.
 *
 * **Bound people comes from the shared stats route, one received row at a time**
 * (`useChannelStats.ts`). A channel this release does not receive on has nobody bound and no
 * figures, and says so with a dash; a row whose figures failed reads "Not available", never nought.
 *
 * **What was removed from the old screen, and why.** The card per channel that drew every
 * identifier, the events address, the adapter's declaration, the health sentence, the bound people
 * with their principal ids, the newest deliveries, the set-up form and the test form one under
 * another for all seven channels: each is on a channel's own page now (Dashboard, Profile, About),
 * with ids under Advanced. The lede that listed everything the page showed, and the served sentence
 * about what a record is, which the About view says for one channel.
 *
 * Task ids: M27.13.1, M27.16.1, M10.1.4
 */

import { MessagesSquare, MoreHorizontal } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useListing } from "../../components/useListing";
import { ListPage, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { GROUP_LABEL, healthWord } from "../channelsQuery";
import { at } from "../operations/parts";
import { ACT_LABELS } from "./channelActions";
import {
  CHANNEL_FILTERS,
  CHANNEL_LIST_API_PATH,
  CHANNEL_SORTS,
  SECRET_UNKNOWN_WHY,
  channelAddress,
  readChannelRows,
  secretWords,
  statusWords,
  type ChannelRow,
} from "./channelRows";
import { HealthPill, StatusPill } from "./pills";
import { useChannelStats, type RowFigures } from "./useChannelStats";

export const CHANNELS_HEADING = "Channels";
export const CHANNELS_LEDE = "The chat channels you manage, whether each is switched on, and how it is doing.";
export const LOADING_CHANNELS = "Loading the channels.";
export const NO_CHANNELS = "No channels to show";
export const NO_CHANNELS_DESCRIPTION = "A channel appears here for each chat surface this release declares that you manage.";
export const CHANNELS_LIST_LABEL = "Channels";
export const FILTERS_LABEL = "Narrow the channels";
export const SEARCH_HINT = "Search channels";

export const CHANNEL_COLUMN = "Channel";
export const STATUS_COLUMN = "Status";
export const SECRET_COLUMN = "Secret";
export const HEALTH_COLUMN = "Health";
export const BOUND_COLUMN = "Bound people";
export const ACTIVE_COLUMN = "Last active";

/** What a cell says while its figures are coming, when they failed, and where there are none. */
export const FIGURES_COMING = "Loading";
export const FIGURES_UNAVAILABLE = "Not available";
export const NO_FIGURES = "-";
export const NEVER_ACTIVE = "Never";

function boundWords(row: ChannelRow, figures: RowFigures): string {
  if (!row.receives) {
    return NO_FIGURES;
  }
  if (figures.kind === "loading") {
    return FIGURES_COMING;
  }
  if (figures.kind === "failed" || figures.stats.boundPeople === undefined) {
    return FIGURES_UNAVAILABLE;
  }
  return figures.stats.boundPeople.toLocaleString("en-GB");
}

function RowMenu({ row }: { readonly row: ChannelRow }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.label}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem asChild>
          <Link to={channelAddress(row.channel)}>{ACT_LABELS.open}</Link>
        </DropdownMenuItem>
        {row.receives ? (
          <DropdownMenuItem asChild>
            <Link to={`${channelAddress(row.channel)}/profile`}>{ACT_LABELS.setUp}</Link>
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ChannelsPage() {
  const listing = useListing<ChannelRow>(CHANNEL_LIST_API_PATH, { choices: CHANNEL_FILTERS });
  const rows = useMemo(() => readChannelRows(listing.body), [listing.body]);
  const received = useMemo(() => rows.filter((row) => row.receives).map((row) => row.channel), [rows]);
  const figuresOf = useChannelStats(received);

  const columns: readonly EntityColumn<ChannelRow>[] = [
    {
      id: "channel",
      header: CHANNEL_COLUMN,
      hideable: false,
      cell: (row) => (
        <Link
          to={channelAddress(row.channel)}
          className="min-w-[8rem] font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline"
        >
          {row.label}
        </Link>
      ),
      text: (row) => row.label,
    },
    { id: "status", header: STATUS_COLUMN, cell: (row) => <StatusPill status={row.status} />, text: (row) => statusWords(row.status) },
    {
      id: "secret",
      header: SECRET_COLUMN,
      cell: (row) => (
        <span className="text-[12.5px] text-body" title={row.secret === "unknown" ? SECRET_UNKNOWN_WHY : undefined}>
          {secretWords(row.secret)}
        </span>
      ),
      text: (row) => secretWords(row.secret),
    },
    { id: "health", header: HEALTH_COLUMN, cell: (row) => <HealthPill health={row.health} />, text: (row) => healthWord(row.health) },
    {
      id: "bound",
      header: BOUND_COLUMN,
      cell: (row) => <span className="font-mono text-[12px] text-ink tabular-nums">{boundWords(row, figuresOf(row.channel))}</span>,
      text: (row) => boundWords(row, figuresOf(row.channel)),
    },
    {
      id: "active",
      header: ACTIVE_COLUMN,
      cell: (row) => (
        <span className="font-mono text-[12px] text-ink tabular-nums">
          {row.last_delivered_at === null ? NEVER_ACTIVE : at(row.last_delivered_at)}
        </span>
      ),
      text: (row) => (row.last_delivered_at === null ? NEVER_ACTIVE : at(row.last_delivered_at)),
    },
  ];

  return (
    <ListPage
      crumbs={[{ label: GROUP_LABEL }, { label: CHANNELS_HEADING }]}
      title={CHANNELS_HEADING}
      lede={CHANNELS_LEDE}
      listing={listing}
      rows={rows}
      filtersLabel={FILTERS_LABEL}
      choices={CHANNEL_FILTERS}
      sorts={CHANNEL_SORTS}
      searchHint={SEARCH_HINT}
      caption={CHANNELS_LIST_LABEL}
      columns={columns}
      rowId={(row) => row.channel}
      rowLabel={(row) => row.label}
      rowActions={(row) => <RowMenu row={row} />}
      exportName="channels"
      loading={LOADING_CHANNELS}
      emptyTitle={NO_CHANNELS}
      emptyDescription={NO_CHANNELS_DESCRIPTION}
      emptyIcon={<MessagesSquare aria-hidden />}
    />
  );
}
