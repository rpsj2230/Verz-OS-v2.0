/**
 * The Dashboard view of one channel, which opens first: what crossed it, how it is doing, and who is
 * bound on it.
 *
 * **The figures are the stats route's, and only what it sent** (`channelStats.ts`): messages
 * received and sent, failures, requests refused, the people bound on it and when anything last
 * crossed it, over the chosen period. While they are on their way the strip says so; if the route
 * fails the strip draws the API's sentence; a figure the route did not send reads "Not recorded
 * yet", never nought. A channel this release does not receive on has no figures and no bound
 * people, and the view says that instead of drawing an empty strip.
 *
 * **The bound people are the binding route's, on the list contract.** Searched, filtered and ordered
 * on the server, named and never shown by id, each with an unbind that is confirmed, says what it
 * does, and is recorded in the audit ledger (CH2's control). How a person binds is one line: from
 * My workspace, with a one-time code they send from the chat.
 *
 * Task ids: M27.13.1, M10.3.4, M10.1.4, M27.16.1
 */

import { useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource, type Resource } from "../../api/useResource";
import type { FilterChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import {
  ConfirmDialog,
  EmptyState,
  EntityTable,
  FailureState,
  ListToolbar,
  LoadingState,
  NotOffered,
  Note,
  SectionCard,
  StatCard,
  StatsStrip,
  type EntityColumn,
} from "../../components/kit";
import { FETCHING_MORE, SHOW_MORE } from "../../components/ListControls";
import { Button } from "../../components/ui/button";
import { cn } from "../../lib/utils";
import { FailureNotice } from "../../ui/FailureNotice";
import { rangeWords } from "../agents/agentStats";
import {
  BOUND_FILTERS,
  BOUND_SORTS,
  bindingsApiPath,
  unbindApiPath,
  type BoundRow,
  type HealthBody,
  type UnboundBody,
} from "../channelsQuery";
import { at } from "../operations/parts";
import { ACT_LABELS, NOT_OFFERED } from "./channelActions";
import type { ChannelRow } from "./channelRows";
import { boundBasisWords, channelPeriodOf, channelStatsApiPath, FIRST_PERIOD, readChannelStats } from "./channelStats";

export const FIGURES_LABEL = "This channel's figures";
export const PERIOD_LABEL = "Period the figures cover";
export const RECEIVED_LABEL = "Received";
export const SENT_LABEL = "Sent";
export const FAILED_LABEL = "Failed";
export const REFUSED_LABEL = "Refused";
export const BOUND_LABEL = "Bound people";
export const LAST_EVENT_LABEL = "Last event";
export const NOTHING_YET = "Nothing yet";
export const REFUSED_SUB = "requests not accepted";
export const NOT_RECEIVED_TITLE = "Not received by this release";
export const NOT_SET_UP_TITLE = "Not set up";
export const NOT_SET_UP_DESCRIPTION = "Save its identifiers and secret on the Profile view, then switch it on.";

export const BOUND_HEADING = "Bound people";
export const READING_BOUND = "Loading who is bound on this channel.";
export const NOBODY_BOUND = "Nobody is bound on this channel";
export const NOBODY_BOUND_DESCRIPTION = "A person appears here once they send the code they asked for in My workspace.";
export const MORE_BOUND = "More people are bound than one list reads, so search to find one.";
export const PERSON_COLUMN = "Person";
export const SINCE_COLUMN = "Bound since";
export const KEEP_LABEL = "Keep them bound";
export const UNBIND_CONSEQUENCE =
  "The Brain stops answering their chat account as them, at once. They can connect it again with a new code. " +
  "The unbinding is recorded in the audit ledger with your name.";
export const NOT_UNBOUND = "The person was not unbound";

const PERIODS = ["7d", "30d"] as const;

function count(value: number | undefined): string | undefined {
  return value === undefined ? undefined : value.toLocaleString("en-GB");
}

function PeriodSwitch({ period, onChange }: { readonly period: string; readonly onChange: (period: string) => void }) {
  return (
    <div role="group" aria-label={PERIOD_LABEL} className="inline-flex rounded-md border border-line bg-sunk p-0.5">
      {PERIODS.map((one) => (
        <button
          key={one}
          type="button"
          aria-pressed={one === period}
          onClick={() => {
            onChange(one);
          }}
          className={cn(
            "min-h-11 rounded-[5px] px-3 text-[12.5px] outline-hidden focus-visible:ring-2 focus-visible:ring-ring sm:min-h-7",
            one === period ? "bg-panel font-medium text-ink shadow-xs" : "text-dim hover:text-ink",
          )}
        >
          {rangeWords(one)}
        </button>
      ))}
    </div>
  );
}

function Figures({ name, version }: { readonly name: string; readonly version: number }) {
  const [period, setPeriod] = useState<string>(FIRST_PERIOD);
  const stats = useResource<unknown>(channelStatsApiPath(name), version);
  const read = stats.data === null ? null : readChannelStats(stats.data);
  const figures = channelPeriodOf(read, period);
  const atLeast = read?.atLeast === true ? "at least" : undefined;
  const failed =
    figures?.failed === undefined
      ? undefined
      : figures.unknown === undefined || figures.unknown === 0
        ? undefined
        : `and ${figures.unknown.toLocaleString("en-GB")} not known`;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="m-0 text-sm font-semibold text-ink">{FIGURES_LABEL}</h2>
        <PeriodSwitch period={period} onChange={setPeriod} />
      </div>
      <StatsStrip label={FIGURES_LABEL} busy={stats.busy} failure={stats.failure} count={6}>
        <StatCard label={RECEIVED_LABEL} value={count(figures?.received)} sub={atLeast} />
        <StatCard label={SENT_LABEL} value={count(figures?.sent)} sub={atLeast} />
        <StatCard label={FAILED_LABEL} value={count(figures?.failed)} sub={failed ?? atLeast} />
        <StatCard label={REFUSED_LABEL} value={count(figures?.refusedInbound)} sub={REFUSED_SUB} />
        <StatCard label={BOUND_LABEL} value={count(read?.boundPeople)} sub={boundBasisWords(read?.boundBasis)} />
        <StatCard
          label={LAST_EVENT_LABEL}
          value={read === null ? undefined : read.lastEvent === undefined ? NOTHING_YET : at(read.lastEvent)}
        />
      </StatsStrip>
    </div>
  );
}

function Bound({ row, version, onChanged }: { readonly row: ChannelRow; readonly version: number; readonly onChanged: (told: string) => void }) {
  const listing = useListing<BoundRow>(bindingsApiPath(row.channel), { choices: BOUND_FILTERS, version });
  const [confirming, setConfirming] = useState<BoundRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const names = useMemo(() => new Map(listing.rows.map((one) => [one.principal_id, one.display_name])), [listing.rows]);
  // The person filter offers people drawn on the list, by name; the value sent is still the id.
  const choices: readonly FilterChoice<BoundRow>[] = useMemo(
    () => BOUND_FILTERS.map((one) => ({ ...one, describe: (value: string) => names.get(value) ?? value })),
    [names],
  );

  const sendUnbinding = (person: BoundRow) => {
    setBusy(true);
    void (async () => {
      const result = await request<UnboundBody>(unbindApiPath(row.channel), {
        method: "POST",
        body: { principal_id: person.principal_id },
      });
      setBusy(false);
      setConfirming(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onChanged(`${person.display_name} is unbound from ${row.label}.`);
    })();
  };

  const columns: readonly EntityColumn<BoundRow>[] = [
    { id: "person", header: PERSON_COLUMN, hideable: false, cell: (one) => one.display_name, text: (one) => one.display_name },
    { id: "since", header: SINCE_COLUMN, cell: (one) => at(one.bound_at), text: (one) => at(one.bound_at) },
  ];
  const truncated = (listing.body as { truncated?: unknown } | null)?.truncated === true;

  let body;
  if (listing.failure !== null) {
    body = <FailureState failure={listing.failure} />;
  } else if (listing.busy) {
    body = <LoadingState label={READING_BOUND} />;
  } else if (listing.rows.length === 0) {
    body = <EmptyState title={NOBODY_BOUND} description={NOBODY_BOUND_DESCRIPTION} />;
  } else {
    body = (
      <EntityTable
        caption={`People bound on ${row.label}`}
        columns={columns}
        rows={listing.rows}
        rowId={(one) => one.principal_id}
        rowLabel={(one) => one.display_name}
        rowActions={(one) => (
          <Button
            variant="outline"
            size="sm"
            className="min-h-11 sm:min-h-8"
            aria-label={`${ACT_LABELS.unbind}: ${one.display_name}`}
            disabled={busy}
            onClick={() => {
              setFailure(null);
              setConfirming(one);
            }}
          >
            {ACT_LABELS.unbind}
          </Button>
        )}
      />
    );
  }

  return (
    <SectionCard
      title={BOUND_HEADING}
      footer={
        <>
          <NotOffered>{NOT_OFFERED.bindForSomebody}</NotOffered>
          {truncated ? <Note>{MORE_BOUND}</Note> : null}
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        <ListToolbar label={`Find a person bound on ${row.label}`} listing={listing} choices={choices} sorts={BOUND_SORTS} />
        {failure === null ? null : <FailureNotice failure={failure} title={NOT_UNBOUND} />}
        {body}
        {listing.moreFailure === null ? null : <FailureState failure={listing.moreFailure} />}
        {listing.fetchingMore ? (
          <p role="status" className="m-0 text-[12.5px] text-dim">
            {FETCHING_MORE}
          </p>
        ) : null}
        {listing.more ? (
          <div>
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
          </div>
        ) : null}
      </div>
      <ConfirmDialog
        open={confirming !== null}
        question={`Unbind ${confirming?.display_name ?? "this person"} from ${row.label}?`}
        consequence={UNBIND_CONSEQUENCE}
        confirmLabel={ACT_LABELS.unbind}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={() => {
          if (confirming !== null) {
            sendUnbinding(confirming);
          }
        }}
        onCancel={() => {
          setConfirming(null);
        }}
      />
    </SectionCard>
  );
}

export function ChannelDashboard({
  row,
  health,
  version,
  onChanged,
}: {
  readonly row: ChannelRow;
  readonly health: Resource<HealthBody>;
  readonly version: number;
  readonly onChanged: (told: string) => void;
}) {
  if (!row.receives) {
    return (
      <EmptyState
        title={NOT_RECEIVED_TITLE}
        description={`This release cannot receive or reply on ${row.label} yet, so it has no figures and nobody can be bound on it.`}
      />
    );
  }
  return (
    <div data-slot="channel-dashboard" className="flex min-w-0 flex-col gap-4">
      <Figures name={row.channel} version={version} />
      {health.data === null ? null : <Note>{health.data.told}</Note>}
      {row.status === "not_set_up" ? (
        <EmptyState title={NOT_SET_UP_TITLE} description={NOT_SET_UP_DESCRIPTION} />
      ) : (
        <Bound row={row} version={version} onChanged={onChanged} />
      )}
    </div>
  );
}
