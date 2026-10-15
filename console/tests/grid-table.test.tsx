/**
 * The table every embedded grid is drawn from, and the property that no grid is drawn any other
 * way: M32.5.2.1 (TanStack Table for every grid).
 *
 * `data-table.test.tsx` holds what the grid must never be able to do (slice, filter, count). This
 * file holds the other half: that there is one way to draw a table, that it draws the three looks
 * the console's tables already had without changing what a screen reader is told, that a cell the
 * reader is typing in is the same element after a render, and that a page cannot add a hand-written
 * `<table>` back without a test going red.
 *
 * Task ids: M32.5.2.1
 */

import { fireEvent, render } from "@testing-library/react";
import { useState } from "react";
import ts from "typescript";
import { describe, expect, test } from "vitest";
import { EntityTable, type EntityColumn } from "../src/components/kit";
import { GridTable } from "../src/components/kit/GridTable";
import type { GridColumn } from "../src/components/gridFeatures";
import { lockedCellKey } from "../src/components/paging";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";

interface Line {
  readonly id: string;
  readonly name: string;
  readonly part: string;
}

const LINES: Line[] = [
  { id: "a", name: "Alpha", part: "one" },
  { id: "b", name: "Bravo", part: "one" },
  { id: "c", name: "Charlie", part: "two" },
];

const COLUMNS: GridColumn<Line>[] = [
  { id: "name", header: "Name", cell: ({ row }) => row.original.name, meta: { rowHeader: true } },
  { id: "part", header: "Part", cell: ({ row }) => row.original.part },
];

function bodyNames(container: HTMLElement): string[] {
  return [...container.querySelectorAll("tbody tr")].map((one) => one.querySelector("th, td")?.textContent ?? "");
}

describe("what the table draws", () => {
  test("every row it was handed is drawn, in the order given, under headings that are column headers", () => {
    // What breaks if this is deleted: the positive half of everything below. A table that drew
    // nothing would satisfy every refusal in this file, so this proves the rows and the headings
    // really come out of the library's model, in the order of the array and not a sorted one.
    const { container } = render(
      <GridTable caption="Lines" columns={COLUMNS} rows={[...LINES].reverse()} rowId={(row) => row.id} />,
    );
    expect(bodyNames(container)).toEqual(["Charlie", "Bravo", "Alpha"]);
    const headings = [...container.querySelectorAll("thead th")];
    expect(headings.map((one) => one.textContent)).toEqual(["Name", "Part"]);
    expect(headings.every((one) => one.getAttribute("scope") === "col")).toBe(true);
    expect(container.querySelector("caption")?.textContent).toBe("Lines");
  });

  test("a column marked as the row's name is a row header and the others are cells", () => {
    // What breaks if this is deleted: a screen reader announcing "Alpha" as one cell among many
    // rather than as the name of the row, which is what the bar lists and the composition diff
    // relied on their hand-written `<th scope="row">` for.
    const { container } = render(<GridTable caption="Lines" columns={COLUMNS} rows={LINES} rowId={(row) => row.id} />);
    const first = container.querySelector("tbody tr");
    expect(first?.querySelector("th")?.getAttribute("scope")).toBe("row");
    expect(first?.querySelectorAll("td")).toHaveLength(1);
  });

  test("the three looks keep the container each screen already had", () => {
    // What breaks if this is deleted: a phone. The `grid` look is the one with the scrolling
    // container around the table (`.grid__scroll`), `kit` is shadcn's own container, and `bare` is
    // nothing at all; moving a table between them changes whether the page or the table scrolls.
    const grid = render(<GridTable look="grid" caption="Lines" columns={COLUMNS} rows={LINES} rowId={(r) => r.id} />);
    expect(grid.container.querySelector(".grid__scroll > table.grid__table")).not.toBeNull();
    const kit = render(<GridTable look="kit" caption="Lines" columns={COLUMNS} rows={LINES} rowId={(r) => r.id} />);
    expect(kit.container.querySelector("[data-slot='table-container'] > table")).not.toBeNull();
    const bare = render(<GridTable caption="Lines" columns={COLUMNS} rows={LINES} rowId={(r) => r.id} />);
    expect(bare.container.firstElementChild?.tagName).toBe("TABLE");
  });

  test("a table without a visible caption is still named, by its caption or its label", () => {
    // What breaks if this is deleted: an unnamed table. Several embedded tables had `aria-label`
    // and no caption; a screen reader lists tables by name, and one with none is "table".
    const hidden = render(<GridTable caption="Lines" captionHidden columns={COLUMNS} rows={LINES} rowId={(r) => r.id} />);
    expect(hidden.container.querySelector("caption")?.className).toContain("sr-only");
    const labelled = render(<GridTable label="The lines" columns={COLUMNS} rows={LINES} rowId={(r) => r.id} />);
    expect(labelled.container.querySelector("table")?.getAttribute("aria-label")).toBe("The lines");
  });

  test("a withheld cell is the one lock and nothing else, and its neighbours still draw", () => {
    // What breaks if this is deleted: the rule `DataTable.tsx` states for the paged grid, kept for
    // the embedded one. A lock that said why would let two readers comparing screens learn which of
    // them was refused. The neighbour is the positive half: a table that locked every cell passes
    // a test that only looks for the lock.
    const { container } = render(
      <GridTable
        caption="Lines"
        columns={COLUMNS}
        rows={LINES}
        rowId={(row) => row.id}
        lockedCells={new Set([lockedCellKey("b", "part")])}
      />,
    );
    const second = container.querySelectorAll("tbody tr")[1];
    expect(second?.querySelectorAll("td")[0]?.querySelector(".lock")).not.toBeNull();
    expect(container.querySelectorAll("tbody tr")[0]?.querySelectorAll("td")[0]?.textContent).toBe("one");
  });

  test("it says nothing about the rows it was not given, and draws no sentence of its own for none", () => {
    // What breaks if this is deleted: a footer count or a "nothing here" on an embedded table. The
    // section that owns a table says what an empty section means, and a total beside a list the
    // reader was filtered to is the hidden rows by subtraction.
    const { container } = render(<GridTable caption="Lines" columns={COLUMNS} rows={[]} rowId={(row) => row.id} />);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(0);
    expect(container.textContent).not.toMatch(/nothing|no \w+ match|\d+ (of|rows)/i);
    const some = render(<GridTable caption="Lines" columns={COLUMNS} rows={LINES} rowId={(row) => row.id} />);
    expect(some.container.textContent).not.toMatch(/\bof\b|\btotal\b|showing/i);
  });
});

describe("what a table may be told about its rows", () => {
  test("rows in runs are one body each under a row-group heading, and an empty table draws none", () => {
    // What breaks if this is deleted: the composition diff's structure. The part heading is a row
    // group a screen reader announces because it heads its own `<tbody>`; one body for the whole
    // table makes it a row that looks different. The empty table is the refusal's sibling: a
    // heading with nothing under it would name a part for a reader with no rows in it.
    const grouped = render(
      <GridTable
        caption="Lines"
        columns={COLUMNS}
        rows={LINES}
        rowId={(row) => row.id}
        groupOf={(row) => row.part}
        groupHeader={(part) => (
          <tr>
            <th scope="rowgroup" colSpan={2}>
              {part}
            </th>
          </tr>
        )}
      />,
    );
    const bodies = [...grouped.container.querySelectorAll("tbody")];
    expect(bodies).toHaveLength(2);
    expect(bodies.map((one) => one.querySelector("th[scope='rowgroup']")?.textContent)).toEqual(["one", "two"]);
    expect(bodies.map((one) => one.querySelectorAll("tr").length)).toEqual([3, 2]);

    const none = render(
      <GridTable
        caption="Lines"
        columns={COLUMNS}
        rows={[]}
        rowId={(row) => row.id}
        groupOf={(row) => row.part}
        groupHeader={() => <tr data-testid="heading" />}
      />,
    );
    expect(none.container.querySelector("[data-testid='heading']")).toBeNull();
  });

  test("a row can be pressable, marked and preceded, and a cell can span the ones a span covers", () => {
    // What breaks if this is deleted: the failover matrix, whose rows open an editor on a press,
    // whose selected row is marked for assistive technology, whose level has a line of its own on a
    // phone and whose empty level says so across the row. Each is a prop of the table and not a
    // hand-written row, so the table can stay the library's.
    let pressed = "";
    const { container } = render(
      <GridTable
        caption="Lines"
        columns={COLUMNS}
        rows={LINES}
        rowId={(row) => row.id}
        rowProps={(row) => ({
          "data-state": row.id === "b" ? "selected" : undefined,
          onClick: () => {
            pressed = row.id;
          },
        })}
        rowBefore={(row) => (row.id === "c" ? <tr data-testid="before-c" /> : null)}
        cellProps={(row, column) => (row.id === "a" && column === "name" ? { colSpan: 2 } : row.id === "a" ? { covered: true } : undefined)}
      />,
    );
    const rows = [...container.querySelectorAll("tbody tr")];
    expect(rows.map((one) => one.getAttribute("data-state"))).toEqual([null, "selected", null, null]);
    expect(rows[2]?.getAttribute("data-testid")).toBe("before-c");
    expect(rows[0]?.querySelectorAll("th, td")).toHaveLength(1);
    expect(rows[0]?.querySelector("th")?.getAttribute("colspan")).toBe("2");
    expect(rows[1]?.querySelectorAll("th, td")).toHaveLength(2);
    fireEvent.click(rows[1] as Element);
    expect(pressed).toBe("b");
  });
});

describe("what a render does to a cell somebody is using", () => {
  /** A form field in a grid, as the connector field map has: a cell holding an input. */
  function Editable() {
    const [text, setText] = useState("");
    // The column is rebuilt on every render, exactly as a page's closure over its own state is.
    const columns: GridColumn<Line>[] = [
      {
        id: "field",
        header: "Field",
        cell: ({ row }) => (
          <input
            aria-label={`Field ${row.original.id}`}
            value={text}
            onChange={(event) => {
              setText(event.target.value);
            }}
          />
        ),
      },
    ];
    return <GridTable caption="Fields" columns={columns} rows={LINES} rowId={(row) => row.id} />;
  }

  test("an input in a cell is the same element, with the focus, after the cell's state changes", () => {
    // What breaks if this is deleted: typing in an editable grid. The library's own `flexRender`
    // mounts a function template as a component, so a column built inside a page is a new
    // component every render and the input is replaced on its first keystroke, taking the focus
    // with it. The connector field map is a grid of inputs; this is the test that would have
    // caught the first character being the last.
    const { getByLabelText } = render(<Editable />);
    const before = getByLabelText("Field a") as HTMLInputElement;
    before.focus();
    fireEvent.change(before, { target: { value: "x" } });
    const after = getByLabelText("Field a") as HTMLInputElement;
    expect(after).toBe(before);
    expect(after.value).toBe("x");
    expect(document.activeElement).toBe(after);
  });

  test("the module list's table keeps a cell's element across a render for the same reason", () => {
    // What breaks if this is deleted: the same loss of focus on every module list, whose columns
    // are written inline on the page and so are new on every render of it.
    function List() {
      const [text, setText] = useState("");
      const columns: EntityColumn<Line>[] = [
        {
          id: "field",
          header: "Field",
          cell: (row) => (
            <input
              aria-label={`Field ${row.id}`}
              value={text}
              onChange={(event) => {
                setText(event.target.value);
              }}
            />
          ),
        },
      ];
      return <EntityTable caption="Fields" columns={columns} rows={LINES} rowId={(row) => row.id} rowLabel={(row) => row.name} />;
    }
    const { getByLabelText } = render(<List />);
    const before = getByLabelText("Field a") as HTMLInputElement;
    before.focus();
    fireEvent.change(before, { target: { value: "y" } });
    expect(getByLabelText("Field a")).toBe(before);
    expect(document.activeElement).toBe(before);
  });
});

describe("no grid is drawn any other way", () => {
  /** The files allowed to write a table element: the two renderers and the shadcn parts they use. */
  const MAY_WRITE_A_TABLE = [
    "src/components/kit/EntityTable.tsx",
    "src/components/kit/GridTable.tsx",
    "src/components/ui/table.tsx",
  ];

  function tableElementsIn(path: string): string[] {
    const found: string[] = [];
    const visit = (node: ts.Node): void => {
      if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
        const name = node.tagName.getText();
        if (name === "table" || name === "Table" || name.endsWith(".Table")) {
          found.push(name);
        }
      }
      ts.forEachChild(node, visit);
    };
    visit(parseConsoleSource(path));
    return found;
  }

  test("no page or component writes a table element of its own", () => {
    // What breaks if this is deleted: "every grid" becoming the list of grids somebody remembered.
    // A page written next month that opens `<table>` draws rows with `.map` inside a body, which
    // can slice, filter or count them with nothing to refuse it. The scan is of every source file,
    // and the positive half is the allow-list itself: each file on it must still write one, or
    // the list is a leftover that would let the next file in unnoticed.
    const offenders = consoleSourcePaths("src")
      .filter((path) => path.endsWith(".tsx"))
      .filter((path) => !MAY_WRITE_A_TABLE.includes(path))
      .filter((path) => tableElementsIn(path).length > 0);
    expect(offenders).toEqual([]);
    for (const path of MAY_WRITE_A_TABLE) {
      expect(tableElementsIn(path).length, path).toBeGreaterThan(0);
    }
  });
});
