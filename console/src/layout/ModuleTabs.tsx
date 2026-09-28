/**
 * The pages of the module being read, as tabs above the page, when the module has more than one.
 *
 * **One menu entry per module, and the module's pages as tabs.** The console plan consolidates
 * pages that show one subject into one module (Part 2.5: Roles, Capabilities and Scopes are Roles
 * and permissions; Logs and Errors are Logs and errors), and until each module is rebuilt as one
 * page its pages are still separate addresses. So the menu has one entry and the pages are these
 * tabs, each a link with an address of its own, and nothing that was reachable stops being so.
 *
 * **The tabs are the API's, like the menu.** They arrive on the entry in the navigation answer, so
 * a department's console, whose entries are narrowed page by page, shows only the pages it was
 * given. A module of one page has none, and no strip is drawn.
 *
 * Task ids: M27.10.1
 */

import { Link, useLocation } from "react-router-dom";
import { entryAt, isAt, type NavGroup } from "./navigationQuery";

interface ModuleTabsProps {
  readonly groups: readonly NavGroup[];
}

export function ModuleTabs({ groups }: ModuleTabsProps) {
  const { pathname } = useLocation();
  const entry = entryAt(groups, pathname);
  if (entry === null || entry.tabs.length < 2) {
    return null;
  }
  return (
    <nav aria-label={entry.label} data-slot="module-tabs" className="mb-4 border-b border-line">
      <ul className="m-0 flex list-none flex-wrap gap-1 p-0">
        {entry.tabs.map((tab) => {
          const here = isAt(pathname, tab.to);
          return (
            <li key={tab.to}>
              <Link
                to={tab.to}
                aria-current={here ? "page" : undefined}
                className={
                  here
                    ? "inline-flex min-h-11 items-center px-3 text-sm font-semibold text-acc-text no-underline shadow-[inset_0_-2px_0_var(--brand)] md:min-h-9"
                    : "inline-flex min-h-11 items-center px-3 text-sm text-body no-underline hover:text-foreground md:min-h-9"
                }
              >
                {tab.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
