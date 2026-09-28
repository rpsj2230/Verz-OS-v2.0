/**
 * One entity's page: the trail to it, a header naming it, the figures every view shares, a switch
 * between its views, and the view.
 *
 * **Each view is an address, so the switch is links and not buttons.** `docs/screens.html` SCREEN 14
 * draws the agent page as one header and three views, each at its own address so a link from an
 * alert or a colleague opens the one it names. A tab strip of buttons would keep the view in state
 * and lose it on reload; links keep it in the address, the back button walks between views, and the
 * keyboard needs no roving handler because a link is already in the tab order. The current view
 * carries `aria-current="page"`. At phone width the switch takes the row in equal columns at 44
 * pixels' height, which fits three labels whole at 360 pixels, the owner's measured case.
 *
 * **The header and its figures sit above the switch**, so every view shares them and none repeats
 * them. What a module puts in the header is its own; this draws the frame.
 *
 * **A view the reader may not open is not in the switch.** The module decides the views from what
 * the API sent this reader and hands over only those; this draws no disabled view, because a greyed
 * tab is a statement that there is something behind it.
 *
 * Task ids: M27.10.2
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "../../lib/utils";
import { Crumbs, type Crumb } from "./PageHeader";
import { initialsOf } from "./parts";

/** One view of an entity, at its own address. */
export interface DetailView {
  readonly key: string;
  readonly label: string;
  readonly to: string;
  readonly icon?: ReactNode | undefined;
}

/** The segmented switch between an entity's views, as links. */
export function ViewSwitch({
  label,
  views,
  current,
}: {
  /** What the switch is, for a screen reader: "Agent views". */
  readonly label: string;
  readonly views: readonly DetailView[];
  /** The key of the view on screen, or nothing when a section outside the switch is shown. */
  readonly current: string | undefined;
}) {
  const columns = views.length === 2 ? "grid-cols-2" : views.length === 3 ? "grid-cols-3" : "grid-cols-4";
  return (
    <nav
      data-slot="view-switch"
      aria-label={label}
      className={cn(
        "[display:grid] w-full rounded-md border border-line bg-sunk p-0.5 sm:w-auto sm:[display:inline-grid]",
        columns,
      )}
    >
      {views.map((view) => {
        const active = view.key === current;
        return (
          <Link
            key={view.key}
            to={view.to}
            aria-current={active ? "page" : undefined}
            className={cn(
              "inline-flex min-h-11 min-w-0 items-center justify-center gap-1.5 rounded-[5px] px-3 text-[13px] no-underline outline-hidden focus-visible:ring-2 focus-visible:ring-ring sm:min-h-8",
              active ? "bg-panel font-medium text-ink shadow-xs" : "text-dim hover:text-ink",
            )}
          >
            {view.icon === undefined ? null : <span className="hidden sm:inline-flex [&>svg]:size-4">{view.icon}</span>}
            {view.label}
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * The header of an entity: its initials where a picture would go, its name, the pills a reader is
 * allowed to see, a line of facts, and its actions.
 */
export function DetailHeader({
  name,
  headingId,
  pills,
  subline,
  actions,
  figures,
  footnote,
}: {
  readonly name: string;
  /** The heading's id, so the page's landmark can be named by it. */
  readonly headingId: string;
  readonly pills?: ReactNode | undefined;
  readonly subline?: ReactNode | undefined;
  readonly actions?: ReactNode | undefined;
  /** A `KpiStrip`, drawn under the identity and shared by every view. */
  readonly figures?: ReactNode | undefined;
  /** A line under the figures, such as what is not recorded yet. */
  readonly footnote?: ReactNode | undefined;
}) {
  return (
    <section
      data-slot="detail-header"
      aria-labelledby={headingId}
      className="overflow-hidden rounded-md border border-line bg-panel"
    >
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span
            aria-hidden
            className="flex size-12 shrink-0 items-center justify-center rounded-full bg-acc-wash font-heading text-[17px] font-semibold text-acc-text"
          >
            {initialsOf(name)}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1
                id={headingId}
                className="m-0 font-heading text-[22px] leading-tight font-semibold tracking-[-0.01em] text-ink [overflow-wrap:anywhere]"
              >
                {name}
              </h1>
              {pills}
            </div>
            {subline === undefined ? null : (
              <p className="m-0 mt-1 font-mono text-[11px] leading-relaxed text-dim [overflow-wrap:anywhere]">{subline}</p>
            )}
          </div>
        </div>
        {actions === undefined ? null : <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {figures === undefined ? null : <div className="border-t border-line [&>dl]:rounded-none [&>dl]:border-0">{figures}</div>}
      {footnote === undefined ? null : <div className="border-t border-line px-4 py-2.5">{footnote}</div>}
    </section>
  );
}

/** The whole frame: trail, header, switch with anything beside it, and the view. */
export function DetailPage({
  crumbs,
  header,
  switcher,
  beside,
  children,
}: {
  readonly crumbs: readonly Crumb[];
  readonly header: ReactNode;
  readonly switcher?: ReactNode | undefined;
  /** Beside the switch, such as a menu of the entity's other sections. */
  readonly beside?: ReactNode | undefined;
  readonly children: ReactNode;
}) {
  return (
    <div data-slot="detail-page" className="flex min-w-0 flex-col gap-4">
      <Crumbs crumbs={crumbs} />
      {header}
      {switcher === undefined && beside === undefined ? null : (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          {switcher}
          {beside === undefined ? null : <div className="flex justify-end">{beside}</div>}
        </div>
      )}
      <div className="min-w-0">{children}</div>
    </div>
  );
}
