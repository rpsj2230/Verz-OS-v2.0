/**
 * A row opens in a drawer without leaving the list: every column, including the ones hidden from the
 * list, in the row's own cells, with focus given back and nothing in it that counts anything.
 *
 * The walk over every page in `list-tools.test.tsx` proves each list has the control. This holds what
 * the control does, on the table alone, where a row's cells are known.
 *
 * Task ids: M27.16.3
 */

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test } from "vitest";
import { EntityTable, type EntityColumn } from "../src/components/kit";
import { DETAILS_DESCRIPTION, detailsLabel } from "../src/components/kit/EntityTable";
import { installRadixStubs } from "./support/radix";

interface Row {
  readonly id: string;
  readonly name: string;
  readonly note: string;
}

const ROWS: readonly Row[] = [
  { id: "a", name: "Ticket triage", note: "Answers the queue" },
  { id: "b", name: "Quote drafter", note: "Drafts quotes" },
];

const COLUMNS: readonly EntityColumn<Row>[] = [
  { id: "name", header: "Agent", hideable: false, cell: (row) => row.name, text: (row) => row.name },
  { id: "note", header: "Note", cell: (row) => row.note, text: (row) => row.note },
  { id: "kept", header: "Kept back", hidden: true, cell: (row) => `hidden for ${row.id}`, text: (row) => row.id },
];

beforeAll(() => {
  installRadixStubs();
});

afterEach(() => {
  cleanup();
});

function table(extra: Partial<Parameters<typeof EntityTable<Row>>[0]> = {}) {
  return render(
    <EntityTable caption="Agents" columns={COLUMNS} rows={ROWS} rowId={(row) => row.id} rowLabel={(row) => row.name} exportName="agents" {...extra} />,
  );
}

describe("the detail drawer", () => {
  test("a row opens in a drawer showing every column, the hidden ones included, and nothing else", async () => {
    // What breaks if this is deleted: a drawer that repeats only what the list shows, which is no
    // reason to open it, or one that draws a figure about the other rows.
    table();
    expect(screen.queryByText("hidden for a")).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: detailsLabel("Ticket triage") }));
    });
    const drawer = await screen.findByRole("dialog");
    // Named in the drawer's title and again by the row's own name column.
    expect(within(drawer).getAllByText("Ticket triage").length).toBeGreaterThan(0);
    expect(within(drawer).getByText(DETAILS_DESCRIPTION)).toBeTruthy();
    expect(within(drawer).getByText("Answers the queue")).toBeTruthy();
    expect(within(drawer).getByText("hidden for a")).toBeTruthy();
    expect(within(drawer).queryByText("Drafts quotes")).toBeNull();
    expect(drawer.textContent).not.toMatch(/\bof\b \d|\d+ (?:rows|results|more)|total/i);
  });

  test("closing it gives focus back to the row's control", async () => {
    // What breaks if this is deleted: a keyboard user who opens a row and is dropped at the top of the
    // page, having lost their place in a long list.
    table();
    const opener = screen.getByRole("button", { name: detailsLabel("Quote drafter") });
    opener.focus();
    await act(async () => {
      fireEvent.click(opener);
    });
    await screen.findByRole("dialog");
    await act(async () => {
      fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(document.activeElement).toBe(opener);
  });

  test("a page with more to say about a row supplies the drawer's body, and a table without a drawer says why on itself", async () => {
    // What breaks if this is deleted: a page's richer view of its own row cannot replace the default,
    // or a table drops the control and leaves no reason for the sweep that holds every list to it.
    const { unmount } = table({ detail: (row) => <p>FULLER-VIEW-OF-{row.id}</p> });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: detailsLabel("Ticket triage") }));
    });
    expect((await screen.findByRole("dialog")).textContent).toContain("FULLER-VIEW-OF-a");
    unmount();

    const { container } = table({ withoutDetail: "Each row of this table is already everything there is to say about it." });
    expect(screen.queryByRole("button", { name: /^Details of/ })).toBeNull();
    expect(container.querySelector("[data-slot='entity-table']")?.getAttribute("data-without-detail")).toContain("already everything");
  });

  test("every row's control is a thumb tall on a phone", () => {
    // What breaks if this is deleted: a 32 pixel control on a phone, where a thumb needs 44.
    table();
    for (const one of screen.getAllByRole("button", { name: /^Details of/ })) {
      expect(one.className).toContain("size-11");
      expect(one.className).toContain("sm:size-8");
    }
  });
});
