/**
 * A row of figures at the top of a page, and one figure in it.
 *
 * **A figure nothing sent is "Not recorded yet", never nought.** Nought is a measurement, and a
 * page that drew one where the API sent nothing would be claiming somebody counted and found none.
 * `StatCard` takes `value` as optional for exactly this: absent draws the sentence, and there is no
 * default a caller could forget to override. See `brain.agent_routes`'
 * `A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT`, which is the same rule on the server. When
 * the API says why a figure is not recorded (the stats routes' `unrecorded` list), the reason is the
 * sentence's tooltip and its accessible description, so a keyboard reaches it as a pointer does.
 *
 * **A strip whose figures are still coming says so, and a strip whose request failed says that.**
 * `StatsStrip` takes the request's state and draws the loading or the failed state in place of the
 * figures, never a row of dashes or zeros while it waits: a zero that turns into 312 a second later
 * was a wrong number on the screen for a second.
 *
 * **No figure here is a count of hidden things.** The strip draws what it is handed, and whoever
 * hands it a figure answers for it being a count over what the reader may see. A figure that
 * could only be computed over rows the reader was not shown does not belong on a page at all.
 *
 * A description list, so each figure is announced as its label and its value together.
 *
 * Task ids: M27.10.2
 */

import { useId, type ReactNode } from "react";
import type { ApiFailure } from "../../api/errors";
import { cn } from "../../lib/utils";
import { Skeleton } from "../ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { FailureState } from "./states";

/** What a figure the API did not send reads as. */
export const NOT_RECORDED = "Not recorded yet";

/** Said while a strip's figures are on their way. */
export const FIGURES_LOADING = "Loading the figures.";

/** The heading over a strip whose request failed. The API's sentence follows it. */
export const FIGURES_FAILED = "The figures could not be loaded";

/**
 * The column classes for a strip of n figures, written out whole so Tailwind finds each one: a
 * class assembled from a number at run time is a class no stylesheet has.
 */
const COLUMNS: Readonly<Record<number, string>> = {
  1: "sm:grid-cols-1",
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
  4: "sm:grid-cols-2 lg:grid-cols-4",
  5: "sm:grid-cols-3 lg:grid-cols-5",
  6: "sm:grid-cols-3 lg:grid-cols-6",
};

/** One figure: a label, a value or the sentence that none was sent, and a line under it. */
/** "Not recorded yet", with the API's reason on hover and on focus when it gave one. */
function NotRecorded({ why }: { readonly why: string | undefined }) {
  const describedBy = useId();
  if (why === undefined) {
    return <>{NOT_RECORDED}</>;
  }
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} aria-describedby={describedBy} className="cursor-help underline decoration-dotted underline-offset-4 outline-hidden focus-visible:ring-2 focus-visible:ring-ring">
            {NOT_RECORDED}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[18rem] text-[12px] leading-snug">
          {why}
        </TooltipContent>
      </Tooltip>
      <span id={describedBy} className="sr-only">
        {why}
      </span>
    </TooltipProvider>
  );
}

export function StatCard({
  label,
  value,
  sub,
  link,
  unrecordedWhy,
}: {
  readonly label: string;
  /** The figure as it should read. Absent means the API sent none: see the note at the top. */
  readonly value?: ReactNode | undefined;
  readonly sub?: ReactNode | undefined;
  /** A link beside the value to where the figure is explained, such as a report. */
  readonly link?: ReactNode | undefined;
  /** Why nothing records this figure, when the API said so. Shown only when there is no value. */
  readonly unrecordedWhy?: string | undefined;
}) {
  const recorded = value !== undefined && value !== null && value !== "";
  return (
    <div data-slot="stat-card" className="flex min-w-0 flex-col gap-0.5 bg-panel px-4 py-3">
      <dt className="font-mono text-[10px] tracking-[0.09em] text-dim uppercase">{label}</dt>
      <dd className="m-0 flex min-w-0 flex-col gap-0.5">
        <span
          className={cn(
            "flex min-w-0 items-baseline gap-1.5 [overflow-wrap:anywhere]",
            recorded
              ? "text-[24px] leading-tight font-semibold tracking-[-0.02em] text-ink tabular-nums"
              : "text-[14px] leading-snug text-dim",
          )}
        >
          {recorded ? value : <NotRecorded why={unrecordedWhy} />}
          {link}
        </span>
        {sub === undefined ? null : <span className="font-mono text-[10.5px] leading-snug text-dim">{sub}</span>}
      </dd>
    </div>
  );
}

/** A row of figures. One column on a phone, and as many as it holds from the small breakpoint. */
export function KpiStrip({
  label,
  count,
  children,
  className,
}: {
  /** What the figures are about, for a screen reader: "This agent's figures". */
  readonly label: string;
  /** How many figures it holds, which decides the columns. */
  readonly count: number;
  readonly children: ReactNode;
  readonly className?: string | undefined;
}) {
  return (
    <dl
      data-slot="kpi-strip"
      aria-label={label}
      className={cn(
        "m-0 [display:grid] grid-cols-1 gap-px overflow-hidden rounded-md border border-line bg-line",
        COLUMNS[count] ?? COLUMNS[3],
        className,
      )}
    >
      {children}
    </dl>
  );
}

/** A strip over a request: its loading state, its failure, or its figures. */
export function StatsStrip({
  label,
  busy,
  failure,
  count,
  children,
}: {
  readonly label: string;
  readonly busy: boolean;
  readonly failure: ApiFailure | null;
  readonly count: number;
  /** The figures, drawn only once the request has answered. */
  readonly children: ReactNode;
}) {
  if (failure !== null) {
    return (
      <div data-slot="stats-strip" aria-label={label} role="group">
        <FailureState failure={failure} title={FIGURES_FAILED} />
      </div>
    );
  }
  if (busy) {
    return (
      <div data-slot="stats-strip" aria-label={label} role="group">
        <div role="status" className="flex flex-col gap-2 rounded-md border border-line bg-panel p-3">
          <Skeleton aria-hidden className="h-12 w-full" />
          <p className="m-0 text-[12.5px] text-dim">{FIGURES_LOADING}</p>
        </div>
      </div>
    );
  }
  return (
    <KpiStrip label={label} count={count}>
      {children}
    </KpiStrip>
  );
}
