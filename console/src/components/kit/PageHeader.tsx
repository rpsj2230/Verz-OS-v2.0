/**
 * The top of every module page: where it sits, what it is called, one sentence saying what it is
 * for, and its primary action.
 *
 * **The breadcrumb is links to real addresses and a last step that is the page itself.** The last
 * step is `BreadcrumbPage`, which carries `aria-current="page"` and is not a link, so nobody is
 * offered a link to where they already are. The trail wraps on a phone, which
 * `tests/ui-structure.test.tsx` holds for the part it is built from.
 *
 * **One primary action, then the rest.** The design of record puts one solid button at the right of
 * a page's heading ("New agent") and everything else quieter. `primary` is that button, or an
 * `UnavailableAction` saying why it cannot be pressed yet; `actions` is the rest.
 *
 * Task ids: M27.10.2
 */

import { Fragment, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "../../lib/utils";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "../ui/breadcrumb";

/** One step of the trail. A step with an address is a link; the last one never is. */
export interface Crumb {
  readonly label: string;
  readonly to?: string | undefined;
}

/** The trail on its own, for a page that draws its own heading. */
export function Crumbs({ crumbs }: { readonly crumbs: readonly Crumb[] }) {
  return (
    <Breadcrumb>
      <BreadcrumbList>
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          return (
            <Fragment key={`${String(index)} ${crumb.label}`}>
              <BreadcrumbItem>
                {last || crumb.to === undefined ? (
                  <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink asChild>
                    <Link to={crumb.to}>{crumb.label}</Link>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
              {last ? null : <BreadcrumbSeparator />}
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

export function PageHeader({
  crumbs,
  title,
  lede,
  primary,
  actions,
  className,
}: {
  readonly crumbs: readonly Crumb[];
  readonly title: string;
  readonly lede?: ReactNode | undefined;
  /** The one solid action. */
  readonly primary?: ReactNode | undefined;
  /** Quieter actions beside it. */
  readonly actions?: ReactNode | undefined;
  readonly className?: string | undefined;
}) {
  return (
    <header data-slot="page-header" className={cn("flex min-w-0 flex-col gap-2", className)}>
      <Crumbs crumbs={crumbs} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="m-0 font-heading text-[22px] leading-tight font-semibold tracking-[-0.01em] text-ink [overflow-wrap:anywhere]">
            {title}
          </h1>
          {lede === undefined ? null : <p className="m-0 mt-1 max-w-[68ch] text-sm text-dim">{lede}</p>}
        </div>
        {primary === undefined && actions === undefined ? null : (
          <div className="flex flex-wrap items-center gap-2">
            {actions}
            {primary}
          </div>
        )}
      </div>
    </header>
  );
}
