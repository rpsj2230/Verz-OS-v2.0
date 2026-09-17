/**
 * The parts of a table: a scrolling container, the table, its head, body and footer, rows, header
 * cells, cells and a caption.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike, with the header
 * text in the muted colour of the design's `th`.
 *
 * **Parts, not a data table, and deliberately without the parts that count.** shadcn/ui's data table
 * example puts "Page 1 of 10" in its pager and "3 of 47 row(s) selected" beside it, and the spike
 * removed both, because a total behind a permission predicate tells a reader how many rows they were
 * not shown (`CLAUDE.md`, and `console.paging.A_PAGE_NEVER_CARRIES_A_COUNT` on the server). The list
 * page that assembles these parts with the server's cursor is W1.3's; `components/DataTable.tsx`
 * stays the one that registers no client row model until then. Nothing here renders a figure of its
 * own, and `tests/ui-rules.test.ts` holds that over the whole directory.
 *
 * **The table scrolls inside its container and the page does not.** The same decision `app.css`
 * records for `.grid__scroll`, for the same measured reason: a table's minimum width is decided by
 * its columns, so on a phone it scrolls sideways inside `overflow-x-auto` or takes the page with it.
 * `tests/ui-structure.test.tsx` reads the compiled rule at a phone's width.
 *
 * Task ids: M27.10.2
 */

import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div data-slot="table-container" className="relative w-full overflow-x-auto">
      <table data-slot="table" className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  );
}

function TableHeader({ className, ...props }: ComponentProps<"thead">) {
  return <thead data-slot="table-header" className={cn("[&_tr]:border-b", className)} {...props} />;
}

function TableBody({ className, ...props }: ComponentProps<"tbody">) {
  return <tbody data-slot="table-body" className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

function TableFooter({ className, ...props }: ComponentProps<"tfoot">) {
  return <tfoot data-slot="table-footer" className={cn("border-t bg-muted/50 font-medium [&>tr]:last:border-b-0", className)} {...props} />;
}

function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn("border-b transition-colors hover:bg-muted/50 has-aria-expanded:bg-muted/50 data-[state=selected]:bg-muted", className)}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-10 px-2 text-left align-middle font-medium whitespace-nowrap text-muted-foreground [&:has([role=checkbox])]:pr-0",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: ComponentProps<"td">) {
  return (
    <td data-slot="table-cell" className={cn("p-2 align-middle whitespace-nowrap text-foreground [&:has([role=checkbox])]:pr-0", className)} {...props} />
  );
}

function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption data-slot="table-caption" className={cn("mt-4 text-sm text-muted-foreground", className)} {...props} />;
}

export { Table, TableHeader, TableBody, TableFooter, TableHead, TableRow, TableCell, TableCaption };
