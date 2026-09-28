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
 * **Changing a limit is coming, not here.** M22.4.1 asks for limits changed from the console within
 * bounds the product fixes; no route does it yet, so the control is `kit/UnavailableAction` with
 * the sentence `operationsActions.ts` gives, and its `retiredBy` pattern retires it the day one lands.
 *
 * **What was removed.** Raw `true` and `false` cells and bare seconds (words now), and the
 * paragraphs explaining why each table is a plain table.
 *
 * Task ids: M27.7.27, M23.1.1, M23.2.1, M27.16.1
 */

import { SlidersHorizontal } from "lucide-react";
import { useResource } from "../../api/useResource";
import { SectionCard, UnavailableAction, type EntityColumn } from "../../components/kit";
import {
  LIMITS_API_PATH,
  readThrottled,
  readUnusual,
  wasRead,
  type Ceiling,
  type Limits as LimitsBody,
  type Throttled,
  type Unusual,
  type Window,
} from "../installQuery";
import { UNAVAILABLE } from "./operationsActions";
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
export const NO_CEILINGS = "No ceilings declared";
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
      primary={
        <UnavailableAction
          label={UNAVAILABLE.changeLimits.label}
          text={UNAVAILABLE.changeLimits.label}
          icon={<SlidersHorizontal aria-hidden />}
          reason={UNAVAILABLE.changeLimits.reason}
        />
      }
      loading={READING_LIMITS}
      busy={answer.busy}
      failure={answer.failure}
      body={answer.data}
    >
      {(page) => {
        const throttled = readThrottled(page);
        const unusual = readUnusual(page);
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
          </>
        );
      }}
    </OpsPage>
  );
}
