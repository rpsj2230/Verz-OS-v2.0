/**
 * The table on every module list: rows as the API sent them, with row selection, a bulk bar,
 * column choice and export of what the reader may see.
 *
 * **It cannot page, filter, sort or count, and that is `components/DataTable.tsx`'s argument kept.**
 * The rows are exactly what the list contract returned for the question on screen (`useListing`),
 * in the order it returned them. A client-side filter would narrow only what already arrived and
 * look identical to the server's, and a total beside a list filtered by permission is the number
 * of rows the reader was not shown. So there is no total, no page count and no "showing 1 to 20";
 * the pager is "Show more" and says only whether there is more.
 *
 * **Why not TanStack here.** `DataTable.tsx` registers none of TanStack's features on purpose, so
 * the library is a renderer there; selection and column choice are two pieces of state, and doing
 * them here keeps every list page importable from the entry chunk without the table library, which
 * `tests/bundle-split.test.ts` would otherwise require to be a lazy route. Rejected: registering
 * `rowSelectionFeature` and `columnVisibilityFeature`, which is what the design spike did. It works,
 * and it puts 40 kB in front of a page that needs two sets.
 *
 * **The bulk bar counts the reader's own selection and nothing else.** "3 selected" is three rows
 * the reader ticked, which are rows they were shown. It never says "of 47". Bulk acts are only the
 * ones a route takes as a set; a module whose writes are one row at a time offers export alone,
 * which reads and changes nothing (`long-lists.test.tsx`' `ONE_ROW_AT_A_TIME`).
 *
 * **Export is the rows drawn, in the columns shown, as the page shows them.** Every row on the page
 * is one the API sent this reader, so the file holds nothing they could not already read, and a
 * column they hid is left out. A cell that begins with a formula character is prefixed so a
 * spreadsheet opens it as text, because a value from the API is data and never a formula.
 *
 * Task ids: M27.10.2
 */

import { Columns3, Download, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";

export const COLUMNS_LABEL = "Columns";
export const SHOW_COLUMNS = "Show columns";
export const EXPORT_LABEL = "Export";
export const EXPORT_SELECTED = "Export selected";
export const CLEAR_SELECTION = "Clear the selection";
export const BULK_ACTIONS_LABEL = "Bulk actions";
export const SELECT_PAGE = "Select every row shown";

/** Said beside the export button, so nobody reads the file as everything that exists. */
export const EXPORT_SAYS_WHAT_IT_HOLDS = "Exports the rows shown here, in the columns shown.";

/** How many a selection is, in words. The reader's own ticks, never a total. */
export function selectedWords(count: number): string {
  return `${String(count)} selected`;
}

export interface EntityColumn<Row> {
  readonly id: string;
  /** The column's heading, and its name in the column menu. */
  readonly header: string;
  readonly cell: (row: Row) => ReactNode;
  /** The cell as text for an export. A column without one is left out of the file. */
  readonly text?: ((row: Row) => string) | undefined;
  /** False for the column that names the row, which can never be hidden. */
  readonly hideable?: boolean | undefined;
  /** Hidden until the reader chooses it. */
  readonly hidden?: boolean | undefined;
  readonly align?: "start" | "end" | undefined;
  readonly className?: string | undefined;
}

/** A spreadsheet opens a cell starting with one of these as a formula. */
const FORMULA_START = /^[=+\-@\t\r]/;

function csvCell(value: string): string {
  const safe = FORMULA_START.test(value) ? `'${value}` : value;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

/** The rows as CSV, in the columns given, with a header line. Pure, so a test can read it. */
export function toCsv<Row>(columns: readonly EntityColumn<Row>[], rows: readonly Row[]): string {
  const exported = columns.filter((column) => column.text !== undefined);
  const lines = [exported.map((column) => csvCell(column.header)).join(",")];
  for (const row of rows) {
    lines.push(exported.map((column) => csvCell(column.text?.(row) ?? "")).join(","));
  }
  return `${lines.join("\r\n")}\r\n`;
}

/** Hand a CSV to the browser as a download. False when this browser cannot make a file. */
export function saveCsv(filename: string, csv: string, into: Document = globalThis.document): boolean {
  if (typeof URL.createObjectURL !== "function") {
    return false;
  }
  const address = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = into.createElement("a");
  link.href = address;
  link.download = filename;
  into.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(address);
  return true;
}

interface EntityTableProps<Row> {
  /** What the table is, for a screen reader. */
  readonly caption: string;
  readonly columns: readonly EntityColumn<Row>[];
  /** Every row drawn so far, exactly as the API sent them. */
  readonly rows: readonly Row[];
  readonly rowId: (row: Row) => string;
  /** The row's name, for "Select Ticket triage". */
  readonly rowLabel: (row: Row) => string;
  /** Acts on the selection. Only acts whose route takes a set; export is offered regardless. */
  readonly bulkActions?: ((selected: readonly Row[], clear: () => void) => ReactNode) | undefined;
  /** The file name an export is saved under, without the extension. No export when absent. */
  readonly exportName?: string | undefined;
  /** An actions cell at the end of each row, such as a menu. */
  readonly rowActions?: ((row: Row) => ReactNode) | undefined;
}

export function EntityTable<Row>({
  caption,
  columns,
  rows,
  rowId,
  rowLabel,
  bulkActions,
  exportName,
  rowActions,
}: EntityTableProps<Row>) {
  const [hidden, setHidden] = useState<ReadonlySet<string>>(
    () => new Set(columns.filter((column) => column.hidden === true).map((column) => column.id)),
  );
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());

  // A tick on a row no longer drawn is dropped, so a changed question never acts on rows the
  // reader can no longer see.
  const drawnIds = useMemo(() => new Set(rows.map(rowId)), [rows, rowId]);
  const selected = rows.filter((row) => picked.has(rowId(row)));
  const selectedIds = new Set([...picked].filter((id) => drawnIds.has(id)));
  const shown = columns.filter((column) => !hidden.has(column.id));
  const selectable = bulkActions !== undefined || exportName !== undefined;
  const allPicked = rows.length > 0 && selectedIds.size === rows.length;
  const somePicked = selectedIds.size > 0 && !allPicked;

  const clear = () => {
    setPicked(new Set());
  };
  const exportRows = (which: readonly Row[]) => {
    if (exportName !== undefined) {
      saveCsv(`${exportName}.csv`, toCsv(shown, which));
    }
  };

  return (
    <div data-slot="entity-table" className="flex min-w-0 flex-col gap-2">
      <div className="flex min-h-9 flex-wrap items-center gap-2">
        {selectedIds.size > 0 ? (
          <div
            role="region"
            aria-label={BULK_ACTIONS_LABEL}
            className="flex min-w-0 flex-1 flex-wrap items-center gap-2 rounded-md border border-line bg-acc-wash px-3 py-1.5"
          >
            <span className="text-sm text-ink" aria-live="polite">
              {selectedWords(selectedIds.size)}
            </span>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {bulkActions?.(selected, clear)}
              {exportName === undefined ? null : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    exportRows(selected);
                  }}
                >
                  <Download aria-hidden /> {EXPORT_SELECTED}
                </Button>
              )}
              <Button size="icon-sm" variant="ghost" aria-label={CLEAR_SELECTION} onClick={clear}>
                <X aria-hidden />
              </Button>
            </div>
          </div>
        ) : (
          <span className="flex-1" />
        )}
        <div className="flex flex-wrap items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8">
                <Columns3 aria-hidden /> {COLUMNS_LABEL}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuLabel>{SHOW_COLUMNS}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {columns
                .filter((column) => column.hideable !== false)
                .map((column) => (
                  <DropdownMenuCheckboxItem
                    key={column.id}
                    checked={!hidden.has(column.id)}
                    onSelect={(event) => {
                      // The menu stays open so several columns can be chosen in one visit.
                      event.preventDefault();
                    }}
                    onCheckedChange={(on) => {
                      const next = new Set(hidden);
                      if (on) {
                        next.delete(column.id);
                      } else {
                        next.add(column.id);
                      }
                      setHidden(next);
                    }}
                  >
                    {column.header}
                  </DropdownMenuCheckboxItem>
                ))}
            </DropdownMenuContent>
          </DropdownMenu>
          {exportName === undefined || rows.length === 0 ? null : (
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              title={EXPORT_SAYS_WHAT_IT_HOLDS}
              onClick={() => {
                exportRows(rows);
              }}
            >
              <Download aria-hidden /> {EXPORT_LABEL}
            </Button>
          )}
        </div>
      </div>

      <div className="min-w-0 overflow-hidden rounded-md border border-line">
        <Table className="text-[13px]">
          <TableCaption className="sr-only">{caption}</TableCaption>
          <TableHeader className="bg-sunk">
            <TableRow className="hover:bg-transparent">
              {selectable ? (
                <TableHead className="w-10">
                  <Checkbox
                    aria-label={SELECT_PAGE}
                    checked={allPicked ? true : somePicked ? "indeterminate" : false}
                    onCheckedChange={(on) => {
                      setPicked(on === true ? new Set(rows.map(rowId)) : new Set());
                    }}
                  />
                </TableHead>
              ) : null}
              {shown.map((column) => (
                <TableHead
                  key={column.id}
                  scope="col"
                  className={cn(
                    "h-9 font-mono text-[10px] tracking-[0.09em] text-dim uppercase",
                    column.align === "end" && "text-right",
                  )}
                >
                  {column.header}
                </TableHead>
              ))}
              {rowActions === undefined ? null : (
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const id = rowId(row);
              const ticked = selectedIds.has(id);
              return (
                <TableRow key={id} data-state={ticked ? "selected" : undefined}>
                  {selectable ? (
                    <TableCell className="w-10 py-2">
                      <Checkbox
                        aria-label={`Select ${rowLabel(row)}`}
                        checked={ticked}
                        onCheckedChange={(on) => {
                          const next = new Set(selectedIds);
                          if (on === true) {
                            next.add(id);
                          } else {
                            next.delete(id);
                          }
                          setPicked(next);
                        }}
                      />
                    </TableCell>
                  ) : null}
                  {shown.map((column) => (
                    <TableCell
                      key={column.id}
                      className={cn("py-2 align-top", column.align === "end" && "text-right", column.className)}
                    >
                      {column.cell(row)}
                    </TableCell>
                  ))}
                  {rowActions === undefined ? null : <TableCell className="w-12 py-1.5">{rowActions(row)}</TableCell>}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
