/**
 * The component layer's structural parts, at a phone's width and from a keyboard: sidebar, tabs,
 * breadcrumb, table, card, drawer and dialog widths, scroll area, separator, skeleton, the empty
 * state and the explanation panel.
 *
 * **How a width is asserted without a browser.** jsdom lays nothing out, and a component styled with
 * utility classes has no stylesheet on disk for `support/cascade.ts` to read. So the stylesheet is
 * compiled here by Tailwind's own compiler over the same sources the build reads
 * (`support/tailwind.ts`), and the cascade reader is handed the compiled rules and a rendered
 * element. What that proves is which declaration a 360 pixel screen applies to the element, which is
 * the same claim `tests/phone-width.test.tsx` makes about the old pages and the same limit: a font's
 * metrics or a browser's rounding are not seen. This is the mechanism the README says the old
 * layout tests move to when a page is restyled.
 *
 * Task ids: M27.10.2
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test, vi } from "vitest";
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "../src/components/ui/breadcrumb";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../src/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "../src/components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "../src/components/ui/empty";
import { Explained } from "../src/components/ui/explained";
import { ScrollArea } from "../src/components/ui/scroll-area";
import { Separator } from "../src/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "../src/components/ui/sheet";
import * as sidebarModule from "../src/components/ui/sidebar";
import {
  SIDEBAR_MENU_LABEL,
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "../src/components/ui/sidebar";
import { Skeleton } from "../src/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../src/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../src/components/ui/tabs";
import { appliesAt, declared, pixels, type OrderedRule } from "./support/cascade";
import { installRadixStubs } from "./support/radix";
import { compileLayer, compiledRules } from "./support/tailwind";
import { parseConsoleSource, propNamesOf } from "./support/typescript";

/** The narrowest phone the console is held to, and a desktop, in CSS pixels. */
const PHONE_PX = 360;
const WIDE_PX = 1280;

let RULES: OrderedRule[] = [];

beforeAll(async () => {
  installRadixStubs();
  RULES = compiledRules((await compileLayer()).css);
}, 60_000);

function setWidth(width: number): void {
  vi.stubGlobal("innerWidth", width);
  window.dispatchEvent(new Event("resize"));
}

const ENTRIES = ["Dashboard", "People", "Agents", "Audit"];

function Shell() {
  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Operate</SidebarGroupLabel>
            <SidebarMenu>
              {ENTRIES.map((entry) => (
                <SidebarMenuItem key={entry}>
                  <SidebarMenuButton asChild isActive={entry === "People"}>
                    <a href={`/${entry.toLowerCase()}`}>{entry}</a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>
      </Sidebar>
      <SidebarInset>
        <SidebarTrigger />
        <main data-legacy>
          <h1>Page</h1>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}

describe("sidebar", () => {
  test("on a desktop the menu is in the page, and the trigger collapses it and says so", () => {
    // What breaks if this is deleted: the desktop half of the shell's navigation. Every entry is a
    // link in the document without opening anything, the current one is marked, and the trigger's
    // `aria-expanded` follows the state it toggles.
    setWidth(WIDE_PX);
    render(<Shell />);
    const trigger = screen.getByRole("button", { name: SIDEBAR_MENU_LABEL });

    expect(ENTRIES.map((entry) => screen.getByRole("link", { name: entry }).getAttribute("href"))).toEqual(
      ENTRIES.map((entry) => `/${entry.toLowerCase()}`),
    );
    expect(screen.getByRole("link", { name: "People" }).getAttribute("data-active")).toBe("true");
    expect(trigger.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(document.querySelector('[data-slot="sidebar"]')?.getAttribute("data-state")).toBe("collapsed");
  });

  test("on a phone the menu is behind a visible Menu button that opens every entry and gives focus back", async () => {
    // What breaks if this is deleted: 5.1's phone navigation. Below 768 pixels the sidebar is a
    // drawer, so the Menu button is the only way to any section: it must be a real button, the drawer
    // must hold every entry, and closing it must put focus back on the button, which Radix does not
    // do for a drawer opened from state.
    setWidth(375);
    render(<Shell />);
    expect(screen.queryByRole("link", { name: "People" })).toBeNull();

    const menu = screen.getByRole("button", { name: SIDEBAR_MENU_LABEL });
    expect(menu.getAttribute("aria-expanded")).toBe("false");
    menu.focus();
    fireEvent.click(menu);

    const drawer = await screen.findByRole("dialog", { name: SIDEBAR_MENU_LABEL });
    for (const entry of ENTRIES) {
      expect(drawer.contains(screen.getByRole("link", { name: entry }))).toBe(true);
    }
    expect(menu.getAttribute("aria-expanded")).toBe("true");

    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(menu);
  });

  test("toggling the sidebar writes no cookie, and there is no count badge to put in it", () => {
    // What breaks if this is deleted: two of the spike's fixes. shadcn/ui writes `sidebar_state` to a
    // cookie on every toggle, which travels to the API with every request; and it ships a menu badge,
    // which is where a count of what a reader cannot open would be drawn (rule R2).
    const cookie = vi.spyOn(Document.prototype, "cookie", "set");
    setWidth(WIDE_PX);
    render(<Shell />);
    fireEvent.click(screen.getByRole("button", { name: SIDEBAR_MENU_LABEL }));
    fireEvent.keyDown(window, { key: "b", ctrlKey: true });

    expect(cookie).not.toHaveBeenCalled();
    expect(Object.keys(sidebarModule).filter((name) => /badge|skeleton/i.test(name))).toEqual([]);
    expect(Object.keys(sidebarModule)).toContain("SidebarMenuButton");
  });
});

describe("tabs and breadcrumb", () => {
  test("the arrow keys move between tabs and show the tab they land on", async () => {
    // What breaks if this is deleted: tabs a keyboard user must Tab through one by one, or whose panel
    // does not follow focus, which is the roving pattern screen readers announce tabs as having.
    render(
      <Tabs defaultValue="overview">
        <TabsList aria-label="Agent">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="skills">Skills</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">What it is for</TabsContent>
        <TabsContent value="skills">What it can do</TabsContent>
      </Tabs>,
    );
    const [overview, skills] = screen.getAllByRole("tab");
    (overview as HTMLElement).focus();
    await act(async () => {
      fireEvent.keyDown(overview as HTMLElement, { key: "ArrowRight" });
    });

    await waitFor(() => expect(document.activeElement).toBe(skills));
    await waitFor(() => expect(screen.getByRole("tabpanel").textContent).toBe("What it can do"));
    expect((skills as HTMLElement).getAttribute("aria-selected")).toBe("true");
  });

  test("a breadcrumb is a labelled landmark whose last step is the page itself, and it wraps on a phone", () => {
    // What breaks if this is deleted: shadcn/ui's current step, a `role="link"` that goes nowhere and
    // is announced as a disabled link; and a trail whose long entity name pushes a phone's page
    // sideways. The width half reads the compiled rules at 360 pixels.
    render(
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="/people">People</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>WeiLingTanWithAVeryLongUnbrokenName</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>,
    );
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    const current = screen.getByText("WeiLingTanWithAVeryLongUnbrokenName");
    const list = nav.querySelector("ol") as Element;

    expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual(["People"]);
    expect(current.getAttribute("aria-current")).toBe("page");
    expect(current.getAttribute("role")).toBeNull();
    expect(declared(list, "flex-wrap", RULES, PHONE_PX)).toBe("wrap");
    expect(declared(list, "overflow-wrap", RULES, PHONE_PX)).toBe("anywhere");
  });
});

describe("widths on a phone", () => {
  test("a table scrolls inside its container on a phone, and the page does not", () => {
    // What breaks if this is deleted: the decision `app.css` records for `.grid__scroll`, lost in the
    // new table: a table's minimum width is decided by its columns, so without a scrolling container
    // it takes the whole page sideways and the navigation with it.
    render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Identifier</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>11111111-1111-4111-8111-111111111111</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    const container = document.querySelector('[data-slot="table-container"]') as Element;
    expect(container.querySelector("table")).not.toBeNull();
    expect(declared(container, "overflow-x", RULES, PHONE_PX)).toBe("auto");
    expect(declared(container, "width", RULES, PHONE_PX)).toBe("100%");
  });

  test("a drawer is most of a phone and never wider, and a dialog keeps a margin on a phone", async () => {
    // What breaks if this is deleted: a drawer capped only by `max-w-sm`, which is 384 pixels on a 360
    // pixel phone, or a dialog with no margin, either of which leaves nothing of the page to tap to
    // close it. The cap applies from the `sm` breakpoint up and not below it, which is asserted too.
    render(
      <>
        <Sheet open>
          <SheetContent>
            <SheetTitle>New webhook</SheetTitle>
            <SheetDescription>Where the events go.</SheetDescription>
          </SheetContent>
        </Sheet>
      </>,
    );
    const sheet = await screen.findByRole("dialog", { name: "New webhook" });
    expect(declared(sheet, "width", RULES, PHONE_PX)).toBe("75%");
    expect(declared(sheet, "max-width", RULES, PHONE_PX)).toBeUndefined();
    expect(declared(sheet, "max-width", RULES, WIDE_PX)).toBe("var(--container-sm)");

    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Details</DialogTitle>
          <DialogDescription>Facts about the row.</DialogDescription>
        </DialogContent>
      </Dialog>,
    );
    const dialog = await screen.findByRole("dialog", { name: "Details" });
    expect(declared(dialog, "max-width", RULES, PHONE_PX)).toBe("calc(100% - 2rem)");
  });

  test("no width a component applies on a phone is wider than the phone", () => {
    // What breaks if this is deleted: `min-w-96` on a popover or `w-[480px]` on a panel, applied at
    // every width, which is the component layer's version of the sideways page `phone-width.test.tsx`
    // holds the old sheets to. Every compiled rule a 360 pixel screen applies is read, so a class
    // added to any component next month is covered the day it is added.
    const checked: string[] = [];
    for (const rule of RULES) {
      if (!appliesAt(rule.atRule, PHONE_PX)) {
        continue;
      }
      for (const property of ["width", "min-width", "inline-size", "min-inline-size", "flex-basis"]) {
        const value = rule.declarations[property];
        if (value === undefined) {
          continue;
        }
        checked.push(`${rule.selector} ${property}`);
        for (const length of value.matchAll(/-?\d*\.?\d+(?:px|rem)\b/g)) {
          expect(pixels(length[0]) ?? 0, `${rule.selector} { ${property}: ${value} }`).toBeLessThanOrEqual(PHONE_PX);
        }
      }
    }
    expect(checked.length).toBeGreaterThan(10);
  });
});

describe("cards, scroll areas and quiet parts", () => {
  test("a card lays its parts out as a column with no width of its own", () => {
    // What breaks if this is deleted: a card with a fixed width, which is a card wider than a phone.
    render(
      <Card>
        <CardHeader>
          <CardTitle>Needs you</CardTitle>
          <CardDescription>Waiting on a decision.</CardDescription>
        </CardHeader>
        <CardContent>Nothing is waiting.</CardContent>
      </Card>,
    );
    const card = document.querySelector('[data-slot="card"]') as Element;
    expect(declared(card, "flex-direction", RULES, PHONE_PX)).toBe("column");
    expect(declared(card, "width", RULES, PHONE_PX)).toBeUndefined();
    expect(screen.getByText("Needs you")).toBeTruthy();
  });

  test("what is inside a scroll area stays reachable from the keyboard", () => {
    // What breaks if this is deleted: a scroll area that hid its content from the tab order, which
    // would make a long list of links unreachable without a pointer.
    render(
      <ScrollArea>
        <a href="/one">One</a>
        <a href="/two">Two</a>
      </ScrollArea>,
    );
    const second = screen.getByRole("link", { name: "Two" });
    second.focus();
    expect(document.activeElement).toBe(second);
    expect(document.querySelector('[data-slot="scroll-area-viewport"]')?.contains(second)).toBe(true);
  });

  test("a decorative separator and a skeleton say nothing to a screen reader, and a real separator does", () => {
    // What breaks if this is deleted: a skeleton announced as content, which a screen reader reads as
    // blank groups while a page loads; and a separator that is part of the structure losing its role.
    render(
      <>
        <Skeleton data-testid="skeleton" />
        <Separator data-testid="decorative" />
        <Separator decorative={false} orientation="vertical" />
      </>,
    );
    expect(screen.getByTestId("skeleton").getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByTestId("decorative").getAttribute("role")).toBe("none");
    expect(screen.getByRole("separator").getAttribute("aria-orientation")).toBe("vertical");
  });
});

describe("empty state and explanation panel", () => {
  test("an empty state's title is a heading at the level the page gives it", () => {
    // What breaks if this is deleted: shadcn/ui's title is a `div`, so an empty page has no heading
    // for a screen reader to land on and the page's outline skips the one thing on it.
    render(
      <Empty>
        <EmptyHeader>
          <EmptyTitle as="h3">No webhooks yet</EmptyTitle>
          <EmptyDescription>An administrator registers one from here.</EmptyDescription>
        </EmptyHeader>
      </Empty>,
    );
    expect(screen.getByRole("heading", { level: 3, name: "No webhooks yet" })).toBeTruthy();
  });

  test("an explanation is one appearance, labelled by its title, and can be told nothing about a reason", () => {
    // What breaks if this is deleted: a `tone`, a `variant` or a `reason` added to the panel, which
    // makes its colour or its icon say which reason applied, and the reason is the part that
    // discloses (`ui/Lock.tsx` takes no props for the same argument). The whole list is asserted,
    // and the positive half: the title labels the note and the action is drawn when there is one.
    expect(propNamesOf(parseConsoleSource("src/components/ui/explained.tsx"), "Explained")).toEqual([
      "title",
      "children",
      "action",
      "headingLevel",
      "className",
    ]);
    render(
      <Explained title="Scheduled jobs are switched off on this install" action={<a href="/features">Open Features</a>}>
        <p>An administrator switches them on.</p>
      </Explained>,
    );
    const note = screen.getByRole("note", { name: "Scheduled jobs are switched off on this install" });
    expect(note.contains(screen.getByRole("link", { name: "Open Features" }))).toBe(true);
  });
});
