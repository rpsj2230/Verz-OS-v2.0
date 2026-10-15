/**
 * The one feature set every grid in this console is built on: TanStack Table with none registered.
 *
 * **It is imported from the entry chunk, and that is a measured decision, not an oversight.** Every
 * list page is a static import of the entry (the route registry collects them with an eager glob),
 * so the table library is in the first response the moment any list renders through it. The
 * feature-less core measures 32 kB minified and 10.7 kB gzipped (esbuild, 2026-10-14) against an
 * entry of 441 kB gzipped, and it is the base of every grid rather than a library one screen
 * needs, which is the difference from `@xyflow/react` and the form libraries that
 * `tests/bundle-split.test.ts` keeps out. Rejected: making sixty route files lazy to keep ten
 * kilobytes out, which puts a loading state in front of every list in the console to save one
 * kilobyte per ten of the entry; and a second barrel for the grid parts, which moved the same
 * import into the same chunk with fifty edited imports.
 *
 * **It is its own module so that two grids share one answer and neither can quietly differ.**
 * `DataTable.tsx` (a page of rows with filter boxes and a pager) and `kit/EntityTable.tsx` (the
 * list a module page draws, with a column choice and a selection) are different components for
 * different jobs, and both render through the library. If each wrote its own `tableFeatures(...)`
 * call, the next person to want a client-side sort would register it in one, and the two grids
 * would answer "what order are these in" differently on two screens of the same console.
 * `tests/data-table.test.tsx` parses every file that imports the library and refuses a feature
 * in any of them, so a third grid cannot opt out by being written elsewhere.
 *
 * **No feature is registered, and that is the mechanism.** `rowPaginationFeature` and
 * `columnFilteringFeature` would put a second, client-side answer next to the API's, and the two
 * look the same on screen; with neither registered, `pageCount`, `rowCount` and
 * `manualPagination` are not options a grid has, so the mistake is a type error and not a
 * behaviour. The two things `EntityTable` does that the library could do (hide a column, tick a
 * row) are held as two sets of state beside it, for `kit/EntityTable.tsx`' reason: registering
 * `columnVisibilityFeature` and `rowSelectionFeature` buys nothing the sets do not, and the
 * features are what a later change would extend into a client-side page.
 *
 * **Why a page's total and page number are not here either.** The argument is `DataTable.tsx`'
 * and `paging.ts`': a count beside a permission-filtered list is the hidden rows by subtraction.
 *
 * Task ids: M32.5.2.1
 */

import { tableFeatures, type ColumnDef, type ColumnDefTemplate, type RowData } from "@tanstack/react-table";
import type { ReactNode } from "react";

/** Per-column settings this console adds. A type-only slot; it registers no feature. */
export interface GridColumnMeta {
  /**
   * The name of the column in a filter box's label. Its presence is what gives the column
   * a filter box, so a column with no server-side filter behind it cannot grow one here by
   * accident.
   */
  readonly filterLabel?: string;
  /**
   * The cell names its row, so it is drawn as a row header (`<th scope="row">`) and a screen
   * reader announces it with every other cell on the row.
   */
  readonly rowHeader?: boolean;
  /** Classes for this column's heading cell, where an embedded table has a look of its own. */
  readonly headerClassName?: string;
  /** Classes for this column's body cells. */
  readonly cellClassName?: string;
}

/**
 * The feature set: none.
 *
 * `columnMeta` is a type-only slot rather than a feature. Every optional feature is left
 * out, and the two that matter are `rowPaginationFeature` and `columnFilteringFeature`.
 */
export const gridFeatures = tableFeatures({ columnMeta: {} as GridColumnMeta });

/** The feature set every column definition and every grid in this console is typed against. */
export type GridFeatures = typeof gridFeatures;

/**
 * A column, typed against the feature set above so a feature-only option cannot be written.
 *
 * `RowData` is the library's own constraint on what a row may be, and it is repeated on
 * every generic here rather than relaxed: a row in this console is an object out of a
 * payload, and widening it would only move the failure to the first cell that tried to read
 * a field off something that has none.
 */
export type GridColumn<T extends RowData> = ColumnDef<GridFeatures, T>;

/**
 * A heading or a cell, drawn by calling its template rather than mounting it.
 *
 * **The library's own `flexRender` is not used, and the reason is a lost cursor.** `flexRender`
 * treats a template that is a function as a React component and mounts it with
 * `createElement(template, props)`. A column written as `cell: ({ row }) => <Input ... />` inside
 * a page is a new function on every render of that page, so React sees a different component type
 * each time and unmounts the old cell and mounts a new one: the input a person is typing in loses
 * its focus after one keystroke, a button they just pressed loses it after the click, and every
 * cell of every row is rebuilt whenever anything above it changes. This is the failure the
 * connector field map (an editable grid) would have had on the first character. A template is a
 * render function here, never a component: it is called with the cell's context, holds no hooks,
 * and what it returns is drawn in place, so the DOM is kept across renders.
 * `tests/grid-table.test.tsx` types into a cell and holds the focus.
 */
export function drawn<P extends object>(template: ColumnDefTemplate<P> | undefined, props: P): ReactNode {
  if (template === undefined) {
    return null;
  }
  return typeof template === "function" ? (template(props) as ReactNode) : template;
}
