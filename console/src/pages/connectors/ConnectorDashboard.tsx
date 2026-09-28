/**
 * The Dashboard view of one source, which opens first: how reading it is going, and what to do.
 *
 * **The figures are the stats route's, and only what it sent** (`connectorStats.ts`): the worker's
 * health word, when it last read the source to the end, its attempts, failures and quota waits over
 * the chosen period, and how many ids of it this install keeps that the reader may read. While they
 * are on their way the strip says so; if the route fails the strip draws the API's sentence; a
 * figure the route did not send reads "Not recorded yet", never nought.
 *
 * **Reading is the worker's own sentence.** What the last attempt came to, or why nothing reads the
 * source, is the `sync` sentence `GET /connectors` serves for the connection, drawn whole.
 *
 * **A declaration that changed says so, with the act that agrees to it.** Editing with the same
 * settings connects the source again under what it declares today, which is the agreement the
 * worker waits for; the button opens the edit.
 *
 * **A source that is not connected has no figures**, and the view says how it is connected instead
 * of drawing an empty strip: from this screen, through Connect Lark, or at the server.
 *
 * Task ids: M27.11.9, M27.16.1
 */

import { useState } from "react";
import { useResource } from "../../api/useResource";
import { EmptyState, Fact, FactList, Note, SectionCard, StatCard, StatsStrip } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { cn } from "../../lib/utils";
import { rangeWords } from "../agents/agentStats";
import { when, type Connected } from "../connectorsQuery";
import { ACT_LABELS } from "./connectorActions";
import { dateWords, healthWords, type SourceDetail } from "./connectorSources";
import { connectorPeriodOf, connectorStatsApiPath, FIRST_PERIOD, idsWords, readConnectorStats } from "./connectorStats";

export const FIGURES_LABEL = "This source's figures";
export const PERIOD_LABEL = "Period the figures cover";
export const HEALTH_LABEL = "Health";
export const LAST_READ_LABEL = "Last read to the end";
export const ATTEMPTS_LABEL = "Attempts";
export const FAILURES_LABEL = "Failures";
export const QUOTA_LABEL = "Quota waits";
export const INDEX_LABEL = "Index size";
export const INDEX_SUB = "ids kept, never values";
export const READING_HEADING = "Reading";
export const NEXT_ATTEMPT = "Next attempt";
export const NOT_CONNECTED_TITLE = "Not connected";
export const AGREE_AGAIN = "Agree to what it declares now";

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

function Figures({ name }: { readonly name: string }) {
  const [period, setPeriod] = useState<string>(FIRST_PERIOD);
  const stats = useResource<unknown>(connectorStatsApiPath(name));
  const read = stats.data === null ? null : readConnectorStats(stats.data);
  const figures = connectorPeriodOf(read, period);
  const atLeast = read?.atLeast === true ? "at least" : undefined;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="m-0 text-sm font-semibold text-ink">{FIGURES_LABEL}</h2>
        <PeriodSwitch period={period} onChange={setPeriod} />
      </div>
      <StatsStrip label={FIGURES_LABEL} busy={stats.busy} failure={stats.failure} count={6}>
        <StatCard label={HEALTH_LABEL} value={read?.health === undefined ? undefined : healthWords(read.health)} />
        <StatCard label={LAST_READ_LABEL} value={dateWords(read?.lastReadToTheEnd)} />
        <StatCard label={ATTEMPTS_LABEL} value={count(figures?.attempts)} sub={atLeast} />
        <StatCard label={FAILURES_LABEL} value={count(figures?.failures)} sub={atLeast} />
        <StatCard label={QUOTA_LABEL} value={count(figures?.quotaWaits)} sub={atLeast} />
        <StatCard label={INDEX_LABEL} value={idsWords(read?.indexIds)} sub={INDEX_SUB} />
      </StatsStrip>
    </div>
  );
}

export function ConnectorDashboard({
  detail,
  connected,
  onEdit,
  onConnectSource,
}: {
  readonly detail: SourceDetail;
  /** The connection as `GET /connectors` describes it, or absent when there is none to show. */
  readonly connected: Connected | undefined;
  /** Opens the edit, for a reader who may make one. */
  readonly onEdit?: (() => void) | undefined;
  /** Opens connecting, for a source this reader may connect from here. */
  readonly onConnectSource?: (() => void) | undefined;
}) {
  const { source } = detail;
  if (source.status === "not_connected") {
    const description =
      source.connectFrom === "console"
        ? "Connect it with the identifiers it asks for and one key. Its settings are kept here and its key in the vault."
        : (detail.elsewhere ?? "");
    return (
      <EmptyState
        title={NOT_CONNECTED_TITLE}
        description={description}
        action={
          onConnectSource === undefined ? undefined : (
            <Button onClick={onConnectSource}>{ACT_LABELS.connect}</Button>
          )
        }
      />
    );
  }
  return (
    <div data-slot="connector-dashboard" className="flex min-w-0 flex-col gap-4">
      {connected === undefined ? null : <Figures name={source.name} />}
      <SectionCard title={READING_HEADING} lede={detail.reading}>
        <div className="flex min-w-0 flex-col gap-3">
          {connected === undefined ? null : (
            <FactList>
              <Fact label="Last attempt">{connected.sync}</Fact>
              {connected.next_sync_at === null ? null : <Fact label={NEXT_ATTEMPT}>{when(connected.next_sync_at)}</Fact>}
            </FactList>
          )}
          {source.declarationChanged && connected !== undefined ? (
            <div className="flex flex-col items-start gap-2">
              <Note>{connected.declaration}</Note>
              {onEdit === undefined ? null : (
                <Button variant="outline" size="sm" onClick={onEdit}>
                  {AGREE_AGAIN}
                </Button>
              )}
            </div>
          ) : null}
        </div>
      </SectionCard>
    </div>
  );
}
