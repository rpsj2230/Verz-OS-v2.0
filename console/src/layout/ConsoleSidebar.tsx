/**
 * The console's menu: the groups the API sent, each with its icon, collapsible, drawn the way
 * `docs/screens.html` SCREEN 1 and SCREEN 2 draw them.
 *
 * **It draws what it is given and decides nothing.** Which groups and entries exist is the API's
 * answer, read by `navigationQuery.ts`, plus the reader's own work from the route files. Nothing
 * here reads a token, a role or a grant, and no entry is added or removed.
 *
 * **Every entry is in the markup on every page, and a closed group hides its entries.** A group is
 * open when it holds the page being read, or when somebody opened it; the others are closed so the
 * menu is nine headings and one open group rather than forty rows. Closing hides rather than
 * removes, because a menu whose markup depended on the page would be a menu that says different
 * things on different pages, and `tests/shell-navigation.test.tsx` holds it to one answer.
 *
 * **A long label wraps rather than being cut.** The label is the link's own text rather than a span,
 * which `components/ui/sidebar.tsx` would truncate, because "Sign-in, directory and sessions" cut
 * to "Sign-in, directory and sessio..." is a module nobody can name.
 *
 * **An entry is current when the page is its own address or one of its tabs'.** A module of several
 * pages is one entry, so Capabilities marks Roles and permissions current, and the tab strip
 * (`ModuleTabs.tsx`) marks which page. `aria-current` says it to a screen reader and the rail and
 * the wash say it to the eye; colour is never the only signal.
 *
 * **No count badge.** The design draws a number beside several entries. A number in the frame of
 * every page is where a count of something the reader may not open could reach the frame, so each
 * number lives on its screen instead, and `components/ui/sidebar.tsx` has no badge to put one in.
 *
 * **Icons are chosen by the group's key, and a key this file does not know gets a plain one.** The
 * key is the API's (`brain.console.screens.ModuleGroup`), so a heading reworded for a reader keeps
 * its icon, and a group added on the server is drawn rather than dropped.
 *
 * Task ids: M27.10.1
 */

import {
  Activity,
  Bot,
  ChartColumn,
  ChevronRight,
  Circle,
  Database,
  House,
  MessageSquare,
  PanelLeftIcon,
  Radio,
  Server,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button } from "../components/ui/button";
import {
  SIDEBAR_MENU_LABEL,
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "../components/ui/sidebar";
import { brandTitle, config } from "../config";
import { entryAt, isAt, type NavGroup, type NavSection } from "./navigationQuery";

/** Said in the menu while the API has not answered which console this is. */
export const MENU_LOADING = "Loading the rest of the menu.";

/** Said in the menu when the API's answer could not be had or could not be read. */
export const MENU_UNAVAILABLE =
  "The rest of the menu could not be loaded, so only the screens about your own work are listed.";

/** What the sidebar says under the product's name, by the console the API gave. */
export const CONSOLE_NAMES: Readonly<Record<"company" | "department", string>> = {
  company: "Company console",
  department: "Department console",
};

/** Where the menu's request stands. */
export type MenuState = "loading" | "unavailable" | "answered";

/** Each group's icon, by the key the API sends. */
const GROUP_ICONS: Readonly<Record<string, LucideIcon>> = {
  use: MessageSquare,
  home: House,
  people: Users,
  agents: Bot,
  knowledge: Database,
  channels: Radio,
  operations: Activity,
  governance: ShieldCheck,
  reports: ChartColumn,
  platform: Server,
};

/** The id a group's heading carries, so its list can name it. */
function headingId(key: string): string {
  return `nav-${key}`;
}

/** Whether a group holds the entry an address belongs to. */
function holds(group: NavGroup, current: NavSection | null): boolean {
  return current !== null && group.sections.includes(current);
}

/**
 * The button that opens the menu on a phone and folds it away on a wider screen.
 *
 * The word is visible beside the icon, because on a phone this button is the only way to any
 * section and an icon alone is a guess. It is a real button, says whether the menu is open, and the
 * drawer gives focus back to it when it closes (`components/ui/focus-return.ts`).
 */
export function MenuButton() {
  const { toggleSidebar, isMobile, open, openMobile } = useSidebar();
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      data-sidebar="trigger"
      aria-expanded={isMobile ? openMobile : open}
      className="min-h-11 gap-2 md:min-h-8"
      onClick={toggleSidebar}
    >
      <PanelLeftIcon aria-hidden="true" />
      <span>{SIDEBAR_MENU_LABEL}</span>
    </Button>
  );
}

interface GroupProps {
  readonly group: NavGroup;
  readonly current: NavSection | null;
  readonly pathname: string;
  readonly open: boolean;
  readonly onToggle: () => void;
  readonly onFollow: () => void;
}

function MenuGroup({ group, current, pathname, open, onToggle, onFollow }: GroupProps) {
  const Icon = GROUP_ICONS[group.key] ?? Circle;
  const id = headingId(group.key);
  return (
    <SidebarGroup className="py-1">
      <h2 id={id} className="m-0 text-xs font-normal">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`${id}-entries`}
          onClick={onToggle}
          className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left font-mono text-xs tracking-wide text-muted-foreground uppercase hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-ring md:min-h-8"
        >
          <Icon aria-hidden="true" className="size-4 shrink-0" />
          <span className="flex-1">{group.heading}</span>
          <ChevronRight
            aria-hidden="true"
            className={open ? "size-3.5 shrink-0 rotate-90 transition-transform" : "size-3.5 shrink-0 transition-transform"}
          />
        </button>
      </h2>
      <SidebarMenu id={`${id}-entries`} aria-labelledby={id} hidden={!open} className="gap-0.5">
        {group.sections.map((section) => {
          const active = section === current;
          return (
            <SidebarMenuItem key={section.to}>
              <SidebarMenuButton asChild isActive={active} className="h-auto min-h-11 pl-8 md:min-h-8 md:py-1.5">
                <Link
                  to={section.to}
                  aria-current={active && isAt(pathname, section.to) ? "page" : active ? "true" : undefined}
                  onClick={onFollow}
                >
                  {section.label}
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          );
        })}
      </SidebarMenu>
    </SidebarGroup>
  );
}

interface ConsoleSidebarProps {
  readonly groups: readonly NavGroup[];
  readonly state: MenuState;
  /** Which console the API gave, or `null` before it has answered. */
  readonly console: "company" | "department" | null;
}

export function ConsoleSidebar({ groups, state, console: given }: ConsoleSidebarProps) {
  const { pathname } = useLocation();
  const { isMobile, setOpenMobile } = useSidebar();
  const current = entryAt(groups, pathname);
  const holding = groups.find((group) => holds(group, current))?.key ?? null;
  // Groups somebody opened or closed by hand, beside the one that holds the page.
  const [toggled, setToggled] = useState<Readonly<Record<string, boolean>>>({});

  // Following a link to another group opens that group, so the current entry is always visible.
  useEffect(() => {
    if (holding !== null) {
      setToggled((was) => (was[holding] === false ? { ...was, [holding]: true } : was));
    }
  }, [holding]);

  const isOpen = (group: NavGroup): boolean =>
    toggled[group.key] ?? (group.key === holding || group.key === "home" || groups.length === 1);

  return (
    <Sidebar>
      <SidebarHeader className="border-b border-sidebar-border px-4 py-3">
        <div className="flex items-center gap-2">
          {config.brand.logoUrl ? <img className="h-6 w-auto max-w-24" src={config.brand.logoUrl} alt="" /> : null}
          <div className="min-w-0">
            <div className="truncate font-heading text-sm font-semibold text-foreground">{brandTitle(config.brand)}</div>
            {given === null ? null : (
              <div className="font-mono text-[0.625rem] tracking-wider text-muted-foreground uppercase">{CONSOLE_NAMES[given]}</div>
            )}
          </div>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label="Sections" className="flex flex-col gap-0.5 py-2">
          {state === "loading" ? (
            <p className="px-4 text-xs text-muted-foreground" role="status">
              {MENU_LOADING}
            </p>
          ) : null}
          {state === "unavailable" ? <p className="px-4 text-xs text-muted-foreground">{MENU_UNAVAILABLE}</p> : null}
          {groups.map((group) => (
            <MenuGroup
              key={group.key}
              group={group}
              current={current}
              pathname={pathname}
              open={isOpen(group)}
              onToggle={() => {
                setToggled((was) => ({ ...was, [group.key]: !isOpen(group) }));
              }}
              onFollow={() => {
                if (isMobile) {
                  setOpenMobile(false);
                }
              }}
            />
          ))}
        </nav>
      </SidebarContent>
    </Sidebar>
  );
}
