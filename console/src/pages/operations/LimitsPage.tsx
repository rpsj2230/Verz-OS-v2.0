/**
 * Rate limits, on the page kit: what is refusing a request now, the windows requests are counted
 * in, the ceilings of the systems the install reads, and who is asking far more than usual.
 *
 * **Two of the four lists are narrowed by the reader's grant, and neither carries a count.** The
 * windows and the ceilings are declarations every reader of this page sees whole; the throttling
 * and unusual lists are matched against the reader's own scope, so a number beside either would be
 * the subtraction disclosure with every figure correct. Nothing here computes a length for display.
 *
 * **An empty list and an absent one are drawn differently.** An empty list is nobody behind a
 * window; an absent one is nothing on this process having looked, drawn as the API's sentence
 * under its heading, because rendering it as the first is the reassuring direction during an
 * incident.
 *
 * **A limit is changed here, within bounds the product fixes** (M22.4.1). `LimitSettings` lists
 * every budget and request window `brain.tuning_routes` serves, and draws a control on each row only
 * for a reader the answer says may change it. Until 2026-09-29 this was `kit/UnavailableAction`
 * saying "coming soon"; the route landed and the act went, in the same commit.
 *
 * **What was removed.** Raw `true` and `false` cells and bare seconds (words now), and the
 * paragraphs explaining why each table is a plain table.
 *
 * **Deferred now names the kinds of work waiting for room** (M22.1.5): the shed plan over the work
 * in progress the install's cache counts, each row a kind of work and the budget whose share it has
 * used, in the order the kinds give way. No figure for what is in use, and none is sent; a process
 * with no cache is the API's sentence under the heading, never an empty table.
 *
 * Task ids: M27.7.27, M23.1.1, M23.2.1, M27.16.1, M22.4.1, M22.1.5
 */

import { useResource } from "../../api/useResource";
import { SectionCard, type EntityColumn } from "../../components/kit";
import {
  LIMITS_API_PATH,
  readDeferred,
  readThrottled,
  readUnusual,
  wasRead,
  type Ceiling,
  type Deferred,
  type Limits as LimitsBody,
  type Throttled,
  type Unusual,
  type Window,
} from "../installQuery";
import { LimitSettings } from "./LimitSettings";
import { durationWords, Line, OpsPage, PLATFORM, WholeList } from "./parts";
import { BandPill, Pill } from "./pills";

export const LIMITS_HEADING = "Rate limits";
export const LIMITS_LEDE = "What is refusing a request now, the windows requests are counted in, and the ceilings of the systems this install reads.";
export const READING_LIMITS = "Loading the limits.";

export const REFUSING_HEADING = "Refusing now";
export const NOTHING_LOOKED = "Nothing here has looked at what is being refused";
export const NOBODY_IS_BEHIND_A_CEILING = "Nothing is refusing a request";
export const NOBODY_IS_BEHIND_A_CEILING_MORE = "A window appears here while it is refusing requests.";
export const WINDOWS_HEADING = "Windows";
export const NO_WINDOWS = "No windows declared";
export const CEILINGS_HEADING = "Ceilings of connected systems";
export const NO_CEILINGS = "No connected source";
/**
 * Said under the empty ceilings list. Found on the owner's install on 2026-09-29: the list named
 * xero, freshdesk and lark_base by their codes with nothing connected; it now holds only the
 * sources this reader may be told are connected, by name (`brain.install_routes`).
 */
export const NO_CEILINGS_MORE = "A source's own limit on requests appears here once it is connected on Connectors.";
export const DEFERRED_HEADING = "Deferred now";
export const NOTHING_COUNTS_WORK = "Nothing here counts the work in progress";
export const NOTHING_IS_DEFERRED = "Nothing is deferred";
export const NOTHING_IS_DEFERRED_MORE = "A kind of work appears here while it has used its share of a budget and waits for room.";
export const UNUSUAL_HEADING = "Asking far more than usual";
export const NOTHING_COUNTED = "Nothing here has counted who is asking more than usual";
export const NOBODY_IS_UNUSUAL = "Nobody is asking far more than usual";
export const NOBODY_IS_UNUSUAL_MORE = "Somebody appears here when their questions are well above their own usual week.";

/** Whose allowance a window counts, in words. A scope this console has not heard of is drawn as itself. */
export const SCOPE_WORDS: Readonly<Record<string, string>> = {
  principal: "A person",
  principal_connector: "A person's share of a system",
  channel: "A channel",
  agent: "An agent",
  connector: "A connected system",
  widget_origin: "A chat widget's site",
};

export function scopeWords(scope: string): string {
  return SCOPE_WORDS[scope] ?? scope;
}

function allowed(limit: number, period: string): string {
  return `${limit.toLocaleString("en-GB")} a ${period}`;
}

const THROTTLE_COLUMNS: readonly EntityColumn<Throttled>[] = [
  { id: "scope", header: "Whose", hideable: false, cell: (row) => scopeWords(row.scope), text: (row) => scopeWords(row.scope) },
  { id: "subject", header: "Who", cell: (row) => row.subject, text: (row) => row.subject },
  { id: "limit", header: "Allowed", align: "end", cell: (row) => row.limit.toLocaleString("en-GB"), text: (row) => String(row.limit) },
  {
    id: "retry",
    header: "Asks again in",
    cell: (row) => durationWords(row.retry_after_seconds),
    text: (row) => durationWords(row.retry_after_seconds),
  },
];

const WINDOW_COLUMNS: readonly EntityColumn<Window>[] = [
  { id: "applies", header: "Applies to", hideable: false, cell: (row) => row.applies_to, text: (row) => row.applies_to },
  { id: "allowed", header: "Allowed", cell: (row) => allowed(row.limit, row.period), text: (row) => allowed(row.limit, row.period) },
  { id: "scope", header: "Whose", hidden: true, cell: (row) => scopeWords(row.scope), text: (row) => scopeWords(row.scope) },
  { id: "window", header: "Window", hidden: true, cell: (row) => durationWords(row.window_seconds), text: (row) => durationWords(row.window_seconds) },
  { id: "unreachable", header: "If the count cannot be read", cell: (row) => row.when_unreachable, text: (row) => row.when_unreachable },
  {
    id: "raisable",
    header: "Can be raised",
    cell: (row) => <Pill>{row.raisable ? "Yes" : "No"}</Pill>,
    text: (row) => (row.raisable ? "Yes" : "No"),
  },
];

const CEILING_COLUMNS: readonly EntityColumn<Ceiling>[] = [
  { id: "name", header: "System", hideable: false, cell: (row) => row.name, text: (row) => row.name },
  { id: "per_day", header: "Per day", align: "end", cell: (row) => row.per_day.toLocaleString("en-GB"), text: (row) => String(row.per_day) },
  {
    id: "raisable",
    header: "Can be raised",
    cell: (row) => <Pill>{row.raisable ? "Yes" : "No"}</Pill>,
    text: (row) => (row.raisable ? "Yes" : "No"),
  },
  {
    id: "derived",
    header: "Worked out from a rate",
    hidden: true,
    cell: (row) => (row.derived ? "Yes" : "No"),
    text: (row) => (row.derived ? "Yes" : "No"),
  },
];

const DEFERRED_COLUMNS: readonly EntityColumn<Deferred>[] = [
  { id: "work", header: "Work", hideable: false, cell: (row) => row.work, text: (row) => row.work },
  { id: "budget", header: "Budget", cell: (row) => row.budget, text: (row) => row.budget },
  {
    id: "share",
    header: "Its share",
    cell: (row) => `${row.share.toLocaleString("en-GB")} of ${row.limit.toLocaleString("en-GB")}`,
    text: (row) => `${String(row.share)} of ${String(row.limit)}`,
  },
  { id: "said", header: "What is deferred", hidden: true, cell: (row) => row.said, text: (row) => row.said },
  { id: "class", header: "Class", hidden: true, cell: (row) => row.workload_class, text: (row) => row.workload_class },
];

const UNUSUAL_COLUMNS: readonly EntityColumn<Unusual>[] = [
  { id: "subject", header: "Who", hideable: false, cell: (row) => row.subject, text: (row) => row.subject },
  {
    id: "band",
    header: "How unusual",
    cell: (row) => <BandPill band={row.band} />,
    text: (row) => row.band,
  },
  { id: "said", header: "What was seen", cell: (row) => row.said, text: (row) => row.said },
];

export function LimitsPage() {
  const answer = useResource<LimitsBody>(LIMITS_API_PATH);
  return (
    <OpsPage
      crumbs={[{ label: PLATFORM }, { label: LIMITS_HEADING }]}
      title={LIMITS_HEADING}
      lede={LIMITS_LEDE}
      loading={READING_LIMITS}
      busy={answer.busy}
      failure={answer.failure}
      body={answer.data}
    >
      {(page) => {
        const throttled = readThrottled(page);
        const unusual = readUnusual(page);
        const deferred = readDeferred(page);
        return (
          <>
            {wasRead(throttled) ? (
              <WholeList
                title={REFUSING_HEADING}
                caption={REFUSING_HEADING}
                columns={THROTTLE_COLUMNS}
                rows={throttled.panel}
                rowId={(row) => `${row.scope}:${row.subject}`}
                rowLabel={(row) => row.subject}
                empty={NOBODY_IS_BEHIND_A_CEILING}
                emptyDescription={NOBODY_IS_BEHIND_A_CEILING_MORE}
              />
            ) : (
              <SectionCard title={REFUSING_HEADING}>
                <p className="m-0 text-sm font-medium text-ink">{NOTHING_LOOKED}</p>
                <Line>{throttled.unread}</Line>
              </SectionCard>
            )}
            {wasRead(deferred) ? (
              <WholeList
                title={DEFERRED_HEADING}
                caption={DEFERRED_HEADING}
                columns={DEFERRED_COLUMNS}
                rows={deferred.panel}
                rowId={(row) => `${row.workload_class}:${row.budget}`}
                rowLabel={(row) => row.said}
                empty={NOTHING_IS_DEFERRED}
                emptyDescription={NOTHING_IS_DEFERRED_MORE}
              />
            ) : deferred.unread ? (
              <SectionCard title={DEFERRED_HEADING}>
                <p className="m-0 text-sm font-medium text-ink">{NOTHING_COUNTS_WORK}</p>
                <Line>{deferred.unread}</Line>
              </SectionCard>
            ) : null}
            <WholeList
              title={WINDOWS_HEADING}
              caption={WINDOWS_HEADING}
              columns={WINDOW_COLUMNS}
              rows={page.windows ?? []}
              rowId={(row) => `${row.scope}:${row.applies_to}:${row.period}`}
              rowLabel={(row) => row.applies_to}
              exportName="rate-limit-windows"
              empty={NO_WINDOWS}
            />
            <WholeList
              title={CEILINGS_HEADING}
              caption={CEILINGS_HEADING}
              columns={CEILING_COLUMNS}
              rows={page.ceilings}
              rowId={(row) => row.name}
              rowLabel={(row) => row.name}
              empty={NO_CEILINGS}
              emptyDescription={NO_CEILINGS_MORE}
            />
            {wasRead(unusual) ? (
              <WholeList
                title={UNUSUAL_HEADING}
                caption={UNUSUAL_HEADING}
                columns={UNUSUAL_COLUMNS}
                rows={unusual.panel}
                rowId={(row) => row.subject}
                rowLabel={(row) => row.subject}
                empty={NOBODY_IS_UNUSUAL}
                emptyDescription={NOBODY_IS_UNUSUAL_MORE}
              />
            ) : unusual.unread ? (
              <SectionCard title={UNUSUAL_HEADING}>
                <p className="m-0 text-sm font-medium text-ink">{NOTHING_COUNTED}</p>
                <Line>{unusual.unread}</Line>
              </SectionCard>
            ) : null}
            <LimitSettings />
          </>
        );
      }}
    </OpsPage>
  );
}
