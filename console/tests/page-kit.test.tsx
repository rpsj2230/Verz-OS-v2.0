/**
 * The shared page kit, one component at a time: what the keyboard can do with it, where focus goes
 * when it closes, and what it does at a phone's width.
 *
 * Every module page is built from these parts, so a regression here is a regression on every page at
 * once, and it is the kind no page test would name: a drawer that stops giving focus back, a table
 * that grows a total, a figure that draws nought for a value nobody sent. Each test says what breaks
 * if it is deleted.
 *
 * **Phone width is read from the compiled component layer**, the rules Tailwind builds for the class
 * names these parts use (`support/tailwind.ts`), at 360 pixels, because jsdom lays out nothing and the
 * old sheets on disk do not hold these rules.
 *
 * Task ids: M27.10.2, M27.10.3
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState, type ReactNode } from "react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router-dom";
import { beforeAll, describe, expect, test, vi } from "vitest";
import type { ApiFailure } from "../src/api/errors";
import {
  Advanced,
  ConfirmDialog,
  DetailHeader,
  Drawer,
  EmptyState,
  EntityTable,
  FailureState,
  FIGURES_FAILED,
  FIGURES_LOADING,
  KpiStrip,
  ListToolbar,
  LoadingState,
  NOT_RECORDED,
  PageHeader,
  RESET_LABEL,
  StatCard,
  StatsStrip,
  toCsv,
  UnavailableAction,
  ViewSwitch,
  type EntityColumn,
} from "../src/components/kit";
import { SELECT_PAGE, selectedWords } from "../src/components/kit/EntityTable";
import { NO_QUESTION, type ListQuestion } from "../src/components/listing";
import type { Listing } from "../src/components/useListing";
import { declared, type OrderedRule } from "./support/cascade";
import { installRadixStubs } from "./support/radix";
import { compileLayer, compiledRules } from "./support/tailwind";

const PHONE_PX = 360;
const WIDE_PX = 1280;
/** A thumb-tall control, as Tailwind compiles `min-h-11` and `h-11`: 44 pixels at the root size. */
const THUMB_TALL = "calc(var(--spacing) * 11)";

let RULES: OrderedRule[] = [];

beforeAll(async () => {
  installRadixStubs();
  RULES = compiledRules((await compileLayer()).css);
}, 60_000);

function escape(): void {
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
}

function OpenedFromState({ children }: { children: (open: boolean, setOpen: (open: boolean) => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open from state
      </button>
      {children(open, setOpen)}
    </>
  );
}

const FAILURE: ApiFailure = {
  status: 500,
  message: "The API explained itself here.",
  traceId: "trace-kit-1",
  outcome: "failed",
  problems: [],
  secondFactorNeeded: false,
};

/** A listing as `useListing` returns it, with the question held in a test's own state. */
function listingOf<Row>(question: ListQuestion, ask: (next: ListQuestion) => void, offered: Record<string, string[]> = {}): Listing<Row> {
  return {
    body: null,
    rows: [],
    failure: null,
    busy: false,
    more: false,
    fetchingMore: false,
    moreFailure: null,
    showMore: () => {},
    question,
    ask,
    offered,
  };
}

// ------------------------------------------------------------------------------ page header

describe("page header", () => {
  test("the trail links every step but the last, which is the page itself, and the actions sit beside the title", () => {
    // What breaks if this is deleted: a trail whose last step is a link to the page you are on, and a
    // primary action a module forgot to draw. Links are in the tab order because they are anchors.
    render(
      <MemoryRouter>
        <PageHeader
          crumbs={[{ label: "Agents", to: "/agents" }, { label: "Ticket triage" }]}
          title="Ticket triage"
          lede="One agent."
          primary={<button type="button">New agent</button>}
        />
      </MemoryRouter>,
    );
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getAllByRole("link").map((one) => one.getAttribute("href"))).toEqual(["/agents"]);
    expect(within(nav).getByText("Ticket triage").getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("heading", { level: 1, name: "Ticket triage" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "New agent" })).toBeTruthy();
  });

  test("on a phone the title breaks inside a long name and the actions wrap under it", () => {
    // What breaks if this is deleted: an agent named with one long word pushing the page sideways,
    // which the agent workspace did at 911 pixels before the phone rules existed.
    const { container } = render(
      <MemoryRouter>
        <PageHeader crumbs={[{ label: "Agents" }]} title="Averyveryverylongunbrokenagentname" primary={<button type="button">Go</button>} />
      </MemoryRouter>,
    );
    const title = container.querySelector("h1") as Element;
    const row = title.parentElement?.parentElement as Element;
    expect(declared(title, "overflow-wrap", RULES, PHONE_PX)).toBe("anywhere");
    expect(declared(row, "flex-wrap", RULES, PHONE_PX)).toBe("wrap");
  });
});

// ------------------------------------------------------------------------------ the toolbar

describe("list toolbar", () => {
  test("typing and choosing change the question asked, and clearing puts back everything but the order", () => {
    // What breaks if this is deleted: a toolbar that filters rows in the browser, which reads as the
    // server's answer and is a statement about what arrived; or a reset that drops the order too.
    const asked: ListQuestion[] = [];
    function Harness() {
      const [question, setQuestion] = useState<ListQuestion>({ ...NO_QUESTION, sort: "department" });
      const listing = listingOf<{ state: string }>(question, (next) => {
        asked.push(next);
        setQuestion(next);
      }, { state: ["enabled", "disabled"] });
      return (
        <ListToolbar
          label="Narrow the agents"
          listing={listing}
          choices={[{ column: "state", label: "Status", everything: "Any status", read: (row) => row.state }]}
          sorts={[
            { value: "", label: "Name" },
            { value: "department", label: "Department" },
          ]}
        />
      );
    }
    render(<Harness />);
    const form = screen.getByRole("search", { name: "Narrow the agents" });
    expect(within(form).queryByRole("button", { name: RESET_LABEL })).toBeNull();

    fireEvent.change(within(form).getByRole("searchbox"), { target: { value: "ticket" } });
    fireEvent.change(within(form).getByLabelText("Status"), { target: { value: "disabled" } });
    expect(asked.at(-1)).toEqual({ search: "ticket", filters: { state: "disabled" }, sort: "department" });
    expect([...within(form).getByLabelText("Status").querySelectorAll("option")].map((one) => one.value)).toEqual([
      "",
      "enabled",
      "disabled",
    ]);

    fireEvent.click(within(form).getByRole("button", { name: new RegExp(RESET_LABEL) }));
    expect(asked.at(-1)).toEqual({ ...NO_QUESTION, sort: "department" });
  });

  test("a filter set to a value no drawn row carries still says what it is set to", () => {
    // What breaks if this is deleted: a select that silently shows "Any status" while the list is
    // narrowed by a value from an earlier page, so the reader cannot see why the list is short.
    const listing = listingOf<{ state: string }>({ ...NO_QUESTION, filters: { state: "archived" } }, () => {}, { state: ["enabled"] });
    render(<ListToolbar label="Narrow" listing={listing} choices={[{ column: "state", label: "Status", everything: "Any", read: (row) => row.state }]} />);
    const select = screen.getByLabelText("Status") as HTMLSelectElement;
    expect(select.value).toBe("archived");
  });

  test("on a phone the search box takes the row and every control is a thumb tall", () => {
    // What breaks if this is deleted: a 256 pixel search box beside three selects on a 360 pixel
    // phone, and controls a cursor can hit and a thumb cannot.
    const listing = listingOf<{ state: string }>(NO_QUESTION, () => {}, { state: ["enabled"] });
    render(<ListToolbar label="Narrow" listing={listing} choices={[{ column: "state", label: "Status", everything: "Any", read: (row) => row.state }]} />);
    const search = screen.getByRole("searchbox");
    expect(declared(search.parentElement as Element, "width", RULES, PHONE_PX)).toBe("100%");
    expect(declared(search, "height", RULES, PHONE_PX)).toBe(THUMB_TALL);
    expect(declared(screen.getByLabelText("Status"), "height", RULES, PHONE_PX)).toBe(THUMB_TALL);
    expect(declared(search.parentElement as Element, "width", RULES, WIDE_PX)).toBe(`calc(var(--spacing) * 64)`);
  });
});

// --------------------------------------------------------------------------------- the table

interface Row {
  readonly id: string;
  readonly name: string;
  readonly note: string;
}

const ROWS: readonly Row[] = [
  { id: "a", name: "Ticket triage", note: "=HYPERLINK(1)" },
  { id: "b", name: "Quote, drafter", note: 'says "hi"' },
];

const COLUMNS: readonly EntityColumn<Row>[] = [
  { id: "name", header: "Agent", hideable: false, cell: (row) => row.name, text: (row) => row.name },
  { id: "note", header: "Note", cell: (row) => row.note, text: (row) => row.note },
  { id: "hidden", header: "Kept back", hidden: true, cell: () => "secret column", text: () => "x" },
];

describe("entity table", () => {
  test("ticking rows shows the reader's own count and never a total, and the header box says some or all", () => {
    // What breaks if this is deleted: "1 of 47 selected", which is 46 facts the reader did not have,
    // or a header box that draws a tick when only some rows are chosen.
    render(<EntityTable caption="Agents" columns={COLUMNS} rows={ROWS} rowId={(row) => row.id} rowLabel={(row) => row.name} exportName="agents" />);
    expect(screen.queryByRole("region", { name: "Bulk actions" })).toBeNull();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Ticket triage" }));
    const bar = screen.getByRole("region", { name: "Bulk actions" });
    expect(bar.textContent).toContain(selectedWords(1));
    expect(bar.textContent).not.toMatch(/ of |total/i);
    expect(screen.getByRole("checkbox", { name: SELECT_PAGE }).getAttribute("aria-checked")).toBe("mixed");

    fireEvent.click(screen.getByRole("checkbox", { name: SELECT_PAGE }));
    expect(screen.getByRole("region", { name: "Bulk actions" }).textContent).toContain(selectedWords(2));
    fireEvent.click(screen.getByRole("button", { name: "Clear the selection" }));
    expect(screen.queryByRole("region", { name: "Bulk actions" })).toBeNull();
  });

  test("the column menu opens from the keyboard, shows a hidden column, and gives focus back", async () => {
    // What breaks if this is deleted: column choice that only a pointer can reach, or one that
    // leaves a keyboard user at the top of the page after they chose.
    render(<EntityTable caption="Agents" columns={COLUMNS} rows={ROWS} rowId={(row) => row.id} rowLabel={(row) => row.name} />);
    expect(screen.queryByText("secret column")).toBeNull();
    const trigger = screen.getByRole("button", { name: /Columns/ });
    trigger.focus();
    await act(async () => {
      fireEvent.keyDown(trigger, { key: "Enter" });
    });
    const menu = await screen.findByRole("menu");
    const item = within(menu).getByRole("menuitemcheckbox", { name: "Kept back" });
    expect(within(menu).queryByRole("menuitemcheckbox", { name: "Agent" })).toBeNull();
    await act(async () => {
      fireEvent.click(item);
    });
    expect(screen.getAllByText("secret column")).toHaveLength(2);
    escape();
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  test("an export is the rows shown in the columns shown, and a cell never opens as a formula", () => {
    // What breaks if this is deleted: an export carrying a column the reader hid, or a value from the
    // API that a spreadsheet runs as a formula when the file is opened.
    const csv = toCsv(COLUMNS.filter((one) => one.hidden !== true), ROWS);
    expect(csv).toBe(`Agent,Note\r\nTicket triage,'=HYPERLINK(1)\r\n"Quote, drafter","says ""hi"""\r\n`);
    expect(csv).not.toContain("Kept back");
  });

  test("on a phone the table scrolls inside its own box and the page does not", () => {
    // What breaks if this is deleted: a table whose columns push the whole page sideways, taking the
    // navigation and the toolbar with it.
    const { container } = render(
      <EntityTable caption="Agents" columns={COLUMNS} rows={ROWS} rowId={(row) => row.id} rowLabel={(row) => row.name} />,
    );
    const box = container.querySelector('[data-slot="table-container"]') as Element;
    expect(declared(box, "overflow-x", RULES, PHONE_PX)).toBe("auto");
  });
});

// ------------------------------------------------------------------------------- the figures

describe("figures", () => {
  test("a figure nothing sent reads as not recorded, and nought is still a figure", () => {
    // What breaks if this is deleted: a strip that draws 0 for a value the API never sent, which is a
    // measurement nobody made, or one that hides a real nought as though it were missing.
    render(
      <KpiStrip label="This agent" count={2}>
        <StatCard label="Runs" value={undefined} />
        <StatCard label="Refused" value={0} />
      </KpiStrip>,
    );
    const strip = screen.getByLabelText("This agent");
    const [runs, refused] = [...strip.querySelectorAll("dd")];
    expect(runs?.textContent).toBe(NOT_RECORDED);
    expect(refused?.textContent).toBe("0");
  });

  test("a strip still coming says so, and a strip that failed shows the API's sentence and reference", () => {
    // What breaks if this is deleted: a row of zeros while the request is in flight, or a failure
    // explained in the console's own words with no reference to follow up.
    const { rerender } = render(
      <StatsStrip label="Figures" busy failure={null} count={1}>
        <StatCard label="Runs" value="3" />
      </StatsStrip>,
    );
    expect(screen.getByRole("status").textContent).toContain(FIGURES_LOADING);
    expect(screen.queryByText("3")).toBeNull();

    rerender(
      <StatsStrip label="Figures" busy={false} failure={FAILURE} count={1}>
        <StatCard label="Runs" value="3" />
      </StatsStrip>,
    );
    expect(document.body.textContent).toContain(FIGURES_FAILED);
    expect(document.body.textContent).toContain(FAILURE.message);
    expect(document.body.textContent).toContain(FAILURE.traceId);
    expect(screen.queryByText("3")).toBeNull();
  });

  test("on a phone the figures stack in one column, and spread out on a wider screen", () => {
    // What breaks if this is deleted: five figures squeezed side by side on a phone, each value
    // wrapping a digit per line.
    render(
      <KpiStrip label="Five" count={5}>
        <StatCard label="A" value="1" />
      </KpiStrip>,
    );
    const strip = screen.getByLabelText("Five");
    expect(declared(strip, "grid-template-columns", RULES, PHONE_PX)).toBe("repeat(1, minmax(0, 1fr))");
    expect(declared(strip, "grid-template-columns", RULES, WIDE_PX)).toBe("repeat(5, minmax(0, 1fr))");
  });
});

// ---------------------------------------------------------------------------- the detail page

describe("detail page", () => {
  test("each view is a link to its own address, the current one says so, and the keyboard reaches all of them", async () => {
    // What breaks if this is deleted: views held in state, which a reload or a shared link loses, or
    // a switch whose current view is only a colour.
    const router = createMemoryRouter(
      [
        {
          path: "/agents/:id/*",
          element: (
            <ViewSwitch
              label="Agent views"
              current="profile"
              views={[
                { key: "dashboard", label: "Dashboard", to: "/agents/a" },
                { key: "profile", label: "Profile", to: "/agents/a/profile" },
                { key: "about", label: "About", to: "/agents/a/about" },
              ]}
            />
          ),
        },
      ],
      { initialEntries: ["/agents/a/profile"] },
    );
    render(<RouterProvider router={router} />);
    const nav = screen.getByRole("navigation", { name: "Agent views" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((one) => one.getAttribute("href"))).toEqual(["/agents/a", "/agents/a/profile", "/agents/a/about"]);
    expect(links.map((one) => one.getAttribute("aria-current"))).toEqual([null, "page", null]);
    for (const link of links) {
      expect(link.tabIndex).toBe(0);
    }
    await act(async () => {
      fireEvent.click(links[2] as Element);
    });
    expect(router.state.location.pathname).toBe("/agents/a/about");
  });

  test("on a phone the switch takes the row in equal columns, every view a thumb tall, and the header stacks", () => {
    // What breaks if this is deleted: three views squeezed into a scrolling strip at 360 pixels, or
    // labels cut short; the owner measured three whole labels at 44 pixels on a phone.
    render(
      <MemoryRouter>
        <ViewSwitch
          label="Views"
          current="a"
          views={[
            { key: "a", label: "Dashboard", to: "/a" },
            { key: "b", label: "Profile", to: "/b" },
            { key: "c", label: "About", to: "/c" },
          ]}
        />
        <DetailHeader name="Ticket triage" headingId="h" actions={<button type="button">Act</button>} />
      </MemoryRouter>,
    );
    const nav = screen.getByRole("navigation", { name: "Views" });
    expect(declared(nav, "grid-template-columns", RULES, PHONE_PX)).toBe("repeat(3, minmax(0, 1fr))");
    expect(declared(nav, "width", RULES, PHONE_PX)).toBe("100%");
    expect(declared(within(nav).getAllByRole("link")[0] as Element, "min-height", RULES, PHONE_PX)).toBe(THUMB_TALL);
    const header = screen.getByRole("heading", { level: 1, name: "Ticket triage" }).closest('[data-slot="detail-header"]') as Element;
    const row = header.firstElementChild as Element;
    expect(declared(row, "flex-direction", RULES, PHONE_PX)).toBe("column");
    expect(declared(row, "flex-direction", RULES, WIDE_PX)).toBe("row");
  });
});

// ------------------------------------------------------------------------ drawer and confirm

describe("drawer", () => {
  test("a drawer opened from state holds focus inside and gives it back to the opener on Escape", async () => {
    // What breaks if this is deleted: a create drawer that leaves a keyboard user at the top of the
    // list when it closes, rather than on the button they pressed.
    render(
      <OpenedFromState>
        {(open, setOpen) => (
          <Drawer open={open} onOpenChange={setOpen} title="New webhook" description="Where the events go." footer={<button type="button">Save</button>}>
            <input aria-label="Address" />
          </Drawer>
        )}
      </OpenedFromState>,
    );
    const opener = screen.getByRole("button", { name: "Open from state" });
    opener.focus();
    fireEvent.click(opener);
    const drawer = await screen.findByRole("dialog", { name: "New webhook" });
    expect(drawer.contains(document.activeElement)).toBe(true);
    escape();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(opener);
  });

  test("on a phone a drawer is most of the screen and never wider than it", async () => {
    // What breaks if this is deleted: a drawer 384 pixels wide on a 360 pixel phone, which leaves no
    // page to tap to close it.
    render(
      <Drawer open onOpenChange={() => {}} title="Edit" description="Change one thing.">
        <p>Body</p>
      </Drawer>,
    );
    const drawer = await screen.findByRole("dialog", { name: "Edit" });
    expect(declared(drawer, "width", RULES, PHONE_PX)).toBe("75%");
    expect(declared(drawer, "max-width", RULES, PHONE_PX)).toBeUndefined();
  });
});

describe("confirm dialog", () => {
  test("it opens on the safe choice, Escape keeps things as they are, and focus goes back to the opener", async () => {
    // What breaks if this is deleted: a confirmation one Enter away from the act it exists to slow
    // down, or one that acts on Escape.
    const confirmed = vi.fn();
    render(
      <OpenedFromState>
        {(open, setOpen) => (
          <ConfirmDialog
            open={open}
            question="Archive Ticket triage?"
            consequence="It stops at once and keeps its history."
            confirmLabel="Archive"
            cancelLabel="Keep it"
            onConfirm={confirmed}
            onCancel={() => setOpen(false)}
          />
        )}
      </OpenedFromState>,
    );
    const opener = screen.getByRole("button", { name: "Open from state" });
    opener.focus();
    fireEvent.click(opener);
    await screen.findByRole("alertdialog", { name: "Archive Ticket triage?" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Keep it" }));
    escape();
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(confirmed).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(opener);
  });

  test("confirming calls the act once and leaves the dialog for the page to close", async () => {
    // What breaks if this is deleted: the positive half. A dialog that closed itself on confirm would
    // draw a refusal after the person had looked away.
    const confirmed = vi.fn();
    const cancelled = vi.fn();
    render(
      <ConfirmDialog
        open
        question="Archive it?"
        consequence="It stops."
        confirmLabel="Archive"
        cancelLabel="Keep it"
        onConfirm={confirmed}
        onCancel={cancelled}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Archive" }));
    expect(confirmed).toHaveBeenCalledTimes(1);
    expect(cancelled).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toBeTruthy();
    expect(declared(screen.getByRole("alertdialog"), "max-width", RULES, PHONE_PX)).toBe("var(--container-xs)");
  });
});

// ----------------------------------------------------------------------------- the small parts

describe("an action that is not built yet", () => {
  test("the keyboard reaches it, it carries its reason, and pressing it does nothing", () => {
    // What breaks if this is deleted: a control drawn live with no route behind it, which is fake
    // functionality; or one removed from the tab order, so a keyboard user never hears why.
    const outside = vi.fn();
    render(
      <div onClickCapture={outside}>
        <UnavailableAction text="Archive" label="Archive" reason="Coming soon: archiving an agent." />
      </div>,
    );
    const control = screen.getByRole("button", { name: "Archive" });
    control.focus();
    expect(document.activeElement).toBe(control);
    expect(control.getAttribute("aria-disabled")).toBe("true");
    expect(control.hasAttribute("disabled")).toBe(false);
    const describedBy = control.getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(describedBy)?.textContent).toBe("Coming soon: archiving an agent.");

    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    control.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(declared(control, "min-height", RULES, PHONE_PX)).toBe(THUMB_TALL);
  });
});

describe("states and the Advanced section", () => {
  test("loading, empty and failed each say something the others do not", () => {
    // What breaks if this is deleted: a spinner with no words, which `screen-states` would catch on a
    // page only after the fact, or a failure with no reference.
    const { container: loading } = render(<LoadingState label="Loading agents." />);
    const { container: empty } = render(<EmptyState title="No agents to show" description="One appears when installed." />);
    const { container: failed } = render(<FailureState failure={FAILURE} />);
    expect(within(loading).getByRole("status").textContent).toContain("Loading agents.");
    expect(empty.textContent).toContain("No agents to show");
    expect(failed.textContent).toContain(FAILURE.message);
    expect(failed.textContent).toContain(FAILURE.traceId);
  });

  test("identifiers wait behind a closed disclosure that the keyboard opens", () => {
    // What breaks if this is deleted: internal ids back on the face of a page, which is the clutter
    // the owner asked to be removed.
    const { container } = render(
      <Advanced>
        <code>quote_helper</code>
      </Advanced>,
    );
    const details = container.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    const summary = details.querySelector("summary") as HTMLElement;
    expect(summary.tabIndex).toBe(0);
    fireEvent.click(summary);
    expect(details.open).toBe(true);
  });
});
