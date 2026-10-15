/**
 * The grid's markup, drawn from TanStack Table's core model: the one place a plain table is
 * rendered in this console outside the module list (`kit/EntityTable.tsx`).
 *
 * **This is what "every grid goes through the library" means for a table that is one section of a
 * record rather than a list.** About twenty tables in the console were hand-written `<table>` or
 * `ui/table` markup: a model's failover steps, a connector's field map, a service account's
 * grants, the deploy history. None of them pages, because each is one bounded section of one
 * answer, so the sentence in the leaf that matters for them is the first half: they render
 * through the library, from column definitions, with the same feature set as every other grid
 * (`gridFeatures.ts`: none registered). A table written in this component cannot slice, filter or
 * count its rows by accident, which a `rows.map(...)` inside a `<tbody>` could and nothing
 * prevented.
 *
 * **The three looks are the three the tables already had, kept so no screen changed.** `grid` is
 * `.grid__scroll` and `.grid__table` (the Records and Models screens), `kit` is the shadcn
 * primitives the newer pages are built from, and `bare` is a plain `<table>` whose classes the
 * caller names. Rejected: one look. The tables differ on purpose (a report's bar table is a
 * different object from a catalogue's grid), and flattening them is a visual change that this
 * task did not ask for and every page test would then have to be re-read for.
 *
 * **A row header is a column setting and not a different component**: `meta.rowHeader` draws the
 * cell as `<th scope="row">`, so a screen reader announces the row's name with each cell on it.
 *
 * **It lives in `components/kit` because that directory is what Tailwind scans.** The `kit` look and
 * the hidden caption are Tailwind utilities, and an old component outside the scanned directories
 * generates none of them (`tests/tailwind-foundation.test.ts` refuses a utility name in an old
 * source, which is how this was found when it sat one directory up). The kit barrel does not
 * re-export it: pages import it from its own path.
 *
 * **It draws what it is given and nothing about what it is not.** No total, no range, no empty
 * sentence of its own (the section that owns the table says what an empty section means), and the
 * locked cell is `ui/Lock` and nothing else, for `DataTable.tsx`' reasons, which are this
 * file's too.
 *
 * Task ids: M32.5.2.1
 */

import { useTable, type Row, type RowData } from "@tanstack/react-table";
import { Fragment, type ComponentPropsWithoutRef, type ElementType, type ReactNode } from "react";
import { cn } from "../../lib/utils";
import { Lock } from "../../ui/Lock";
import { drawn, gridFeatures, type GridColumn } from "../gridFeatures";
import { filterValueBudget, lockedCellKey } from "../paging";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";

/** Which of the three markups a table is drawn in. */
export type GridLook = "grid" | "kit" | "bare";

/** The elements a table is made of, so one body of code draws all three looks. */
interface Parts {
  readonly Table: ElementType;
  readonly Caption: ElementType;
  readonly Head: ElementType;
  readonly Body: ElementType;
  readonly Row: ElementType;
  readonly Th: ElementType;
  readonly Td: ElementType;
}

const PLAIN_PARTS: Parts = { Table: "table", Caption: "caption", Head: "thead", Body: "tbody", Row: "tr", Th: "th", Td: "td" };
const KIT_PARTS: Parts = {
  Table,
  Caption: TableCaption,
  Head: TableHeader,
  Body: TableBody,
  Row: TableRow,
  Th: TableHead,
  Td: TableCell,
};

const NO_LOCKS: ReadonlySet<string> = new Set();
const NO_FILTERS: Readonly<Record<string, string>> = Object.freeze({});

/** What a table may set on one body row: its classes, `data-` attributes and a press handler. */
export type GridRowProps = ComponentPropsWithoutRef<"tr"> & { readonly [name: `data-${string}`]: string | undefined };

/** What one cell of one row may be told: to span columns, or to be left out because another spans it. */
export interface GridCellProps {
  readonly colSpan?: number | undefined;
  /** The cell is covered by a spanning cell before it, so it is not drawn. */
  readonly covered?: boolean | undefined;
  /** Classes for this cell in place of its column's, where one row's cell does not look like the rest. */
  readonly className?: string | undefined;
}

export interface GridTableProps<T extends RowData> {
  readonly columns: readonly GridColumn<T>[];
  /** Exactly the rows to draw, in the order given. Never a superset to be sliced. */
  readonly rows: readonly T[];
  /** The record's own identifier, which a lock is matched against. */
  readonly rowId: (row: T) => string;
  /** What the table is. Drawn as a `<caption>` when given, and read by a screen reader. */
  readonly caption?: string | undefined;
  /** The caption is for a screen reader only, because the section's heading already says it. */
  readonly captionHidden?: boolean | undefined;
  /** Classes on the caption, where an embedded table has a look of its own. */
  readonly captionClassName?: string | undefined;
  /** The table's name when it has no caption. */
  readonly label?: string | undefined;
  readonly look?: GridLook | undefined;
  /** Classes on the `<table>`. */
  readonly className?: string | undefined;
  /** Classes on the `<thead>`. */
  readonly headClassName?: string | undefined;
  /** Classes on the heading row. */
  readonly headRowClassName?: string | undefined;
  /** Classes on one body row. */
  readonly rowClassName?: ((row: T) => string | undefined) | undefined;
  /** Attributes for one body row, where a row is pressable or marked (the failover matrix). */
  readonly rowProps?: ((row: T) => GridRowProps | undefined) | undefined;
  /** Drawn directly above one body row, such as a level's own line on a phone. */
  readonly rowBefore?: ((row: T) => ReactNode) | undefined;
  /** What one cell is told: a span, or that a span before it covers it. */
  readonly cellProps?: ((row: T, column: string) => GridCellProps | undefined) | undefined;
  /**
   * Which group a row belongs to, for a table whose rows come in runs under a heading (a diff by
   * part). Each run is its own `<tbody>`, headed by `groupHeader`, which is what makes the heading a
   * row group a screen reader announces rather than a row that happens to look different.
   */
  readonly groupOf?: ((row: T) => string) | undefined;
  readonly groupHeader?: ((group: string) => ReactNode) | undefined;
  /** Keys from `lockedCellKey` for cells the API withheld. */
  readonly lockedCells?: ReadonlySet<string> | undefined;
  /** The filter each column is currently asking for, by column id. */
  readonly filters?: Readonly<Record<string, string>> | undefined;
  /** Called as somebody types. The value goes to the API, never to these rows. */
  readonly onFilterChange?: ((column: string, value: string) => void) | undefined;
}

export function GridTable<T extends RowData>({
  columns,
  rows,
  rowId,
  caption,
  captionHidden = false,
  captionClassName,
  label,
  look = "bare",
  className,
  headClassName,
  headRowClassName,
  rowClassName,
  rowProps,
  rowBefore,
  cellProps,
  groupOf,
  groupHeader,
  lockedCells = NO_LOCKS,
  filters = NO_FILTERS,
  onFilterChange,
}: GridTableProps<T>) {
  const table = useTable({
    features: gridFeatures,
    columns: [...columns],
    data: rows,
    getRowId: (row: T) => rowId(row),
  });

  const filterable = table
    .getFlatHeaders()
    .some((header) => header.column.columnDef.meta?.filterLabel !== undefined);

  const P = look === "kit" ? KIT_PARTS : PLAIN_PARTS;
  const captionClass = look === "grid" ? "grid__caption" : look === "kit" ? "mt-0 mb-2 text-left" : captionClassName;

  const drawRow = (row: Row<typeof gridFeatures, T>): ReactNode => (
    <Fragment key={row.id}>
      {rowBefore?.(row.original)}
      <P.Row {...rowProps?.(row.original)} className={cn(rowClassName?.(row.original), rowProps?.(row.original)?.className)}>
        {row.getAllCells().map((cell) => {
          const meta = cell.column.columnDef.meta;
          const told = cellProps?.(row.original, cell.column.id);
          if (told?.covered === true) {
            return null;
          }
          const content = lockedCells.has(lockedCellKey(row.id, cell.column.id)) ? (
            <Lock />
          ) : (
            drawn(cell.column.columnDef.cell, cell.getContext())
          );
          return meta?.rowHeader === true ? (
            <P.Th key={cell.id} scope="row" colSpan={told?.colSpan} className={told?.className ?? meta.cellClassName}>
              {content}
            </P.Th>
          ) : (
            <P.Td key={cell.id} colSpan={told?.colSpan} className={told?.className ?? meta?.cellClassName}>
              {content}
            </P.Td>
          );
        })}
      </P.Row>
    </Fragment>
  );

  // Runs of consecutive rows in one group, in the order given. Without a grouping the whole table
  // is one body, which is also what a table with no rows draws.
  const groups: { name: string; rows: Row<typeof gridFeatures, T>[] }[] = [];
  for (const row of table.getRowModel().rows) {
    const name = groupOf?.(row.original) ?? "";
    const last = groups[groups.length - 1];
    if (last !== undefined && last.name === name) {
      last.rows.push(row);
    } else {
      groups.push({ name, rows: [row] });
    }
  }
  if (groups.length === 0) {
    groups.push({ name: "", rows: [] });
  }

  const markup = (
    <P.Table
      className={cn(look === "grid" && "grid__table", className)}
      aria-label={label}
    >
      {caption === undefined ? null : (
        <P.Caption className={cn(captionClass, captionHidden && "sr-only")}>{caption}</P.Caption>
      )}
      <P.Head className={headClassName}>
        <P.Row className={headRowClassName}>
          {table.getFlatHeaders().map((header) => (
            <P.Th
              key={header.id}
              scope="col"
              className={header.column.columnDef.meta?.headerClassName}
            >
              {drawn(header.column.columnDef.header, header.getContext())}
            </P.Th>
          ))}
        </P.Row>
        {filterable ? (
          <P.Row className="grid__filters">
            {table.getFlatHeaders().map((header) => {
              const filterLabel = header.column.columnDef.meta?.filterLabel;
              return (
                <P.Td key={header.id}>
                  {filterLabel === undefined ? null : (
                    <input
                      type="text"
                      className="grid__filter"
                      aria-label={`Filter by ${filterLabel}`}
                      // The term the route accepts, less what the column name and the separator
                      // take. Spent here rather than on the way out, because a term trimmed as it
                      // is sent asks a different question and answers it convincingly; one a
                      // person cannot finish typing is visible.
                      maxLength={filterValueBudget(header.column.id)}
                      value={filters[header.column.id] ?? ""}
                      onChange={(event) => {
                        onFilterChange?.(header.column.id, event.target.value);
                      }}
                    />
                  )}
                </P.Td>
              );
            })}
          </P.Row>
        ) : null}
      </P.Head>
      {groups.map((group) => (
        <P.Body key={group.name}>
          {groupHeader === undefined || group.rows.length === 0 ? null : groupHeader(group.name)}
          {group.rows.map(drawRow)}
        </P.Body>
      ))}
    </P.Table>
  );
  // The scrolling container is the table's parent and the pager's sibling, for the reason
  // `app.css` records at `.grid__scroll`.
  return look === "grid" ? <div className="grid__scroll">{markup}</div> : markup;
}
