/**
 * The failover matrix as the owner drew it on 2026-09-03 and restated on 2026-09-29: one card, its
 * title and an information mark, and one table of Complexity, Step, Provider, Model and Role. The
 * Models page and the Routing page draw this same card, so the two can never disagree about what
 * the matrix looks like.
 *
 * **Nothing on the card but the table.** No lede under the title (the one sentence explaining it is
 * the information mark's, and is also written for a screen reader beside it), no search, no filter
 * and no column of buttons: a dozen steps are read whole, in the one order a question walks them,
 * and a narrowed matrix is not the chain anybody's question takes. The rows are thin and uniform, a
 * level is named on its first row only, the step number is in the accent, the model in small
 * monospace, the first step's role is the rounded "default" pill and every later role is quiet
 * words. A marker, such as "No key", sits beside the role of a step the next question will not use.
 *
 * **Acting on a step is quiet until it is wanted.** Where the page lets its reader change the
 * matrix, pressing a row opens that step's editor, and a "..." menu at the row's end, drawn on
 * hover or focus and always on a phone, offers the same and, on the Routing page, moving the step
 * and retiring it. The row press is the mouse's shortcut; the menu is a native button and is the
 * keyboard's way to every one of those acts, so nothing here needs a handler of its own. Every act
 * that changes the matrix is handed to the page, which confirms it before sending.
 *
 * Task ids: M5.3.3, M27.15.38, M27.16.1
 */

import { ArrowDown, ArrowUp, Info, MoreHorizontal } from "lucide-react";
import { useId, type ReactNode } from "react";
import type { GridColumn } from "../../components/gridFeatures";
import { GridTable } from "../../components/kit/GridTable";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { TableCell, TableRow } from "../../components/ui/table";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../../components/ui/tooltip";
import { NO_STEP_FOR_THE_LEVEL } from "../modelsQuery";
import { MarkerPill, RolePill } from "./pills";
import { EDIT_STEP, MOVE_DOWN, MOVE_UP, RETIRE_STEP, type MatrixLine } from "./routingWords";

export const FAILOVER_MATRIX = "Failover matrix: what answers, and what happens when it fails";
export const MATRIX_EXPLAINED =
  "A question is answered by its level's first step. When a step fails, is too slow or is turned away, the next step is tried.";
export const ABOUT_THE_MATRIX = "About the failover matrix";

/** A change to one step the page confirms before sending: a move up or down, or a retirement. */
export type StepAsk =
  | { readonly kind: "move"; readonly line: MatrixLine; readonly rungId: string; readonly step: number }
  | { readonly kind: "retire"; readonly line: MatrixLine; readonly rungId: string };

/** What the card may do with a step, for a reader the page says may change the matrix. */
export interface MatrixActs {
  /** Open the step's editor. A row press and the menu's first item both call it. */
  readonly open: (line: MatrixLine) => void;
  /** Move or retire the step, where the page sends those. Absent, the menu offers only Edit. */
  readonly ask?: ((asked: StepAsk) => void) | undefined;
}

/** The information mark after the title, its sentence on hover and focus and for a screen reader. */
function AboutTheMatrix() {
  const describedBy = useId();
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={ABOUT_THE_MATRIX}
            aria-describedby={describedBy}
            className="inline-flex size-6 shrink-0 items-center justify-center rounded-full text-dim outline-hidden hover:text-ink focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Info aria-hidden className="size-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[20rem] text-[12px] leading-snug">
          {MATRIX_EXPLAINED}
        </TooltipContent>
      </Tooltip>
      <span id={describedBy} className="sr-only">
        {MATRIX_EXPLAINED}
      </span>
    </TooltipProvider>
  );
}

function StepMenu({ line, acts }: { readonly line: MatrixLine; readonly acts: MatrixActs }) {
  const rung = line.rung;
  if (rung === null || line.step === null) {
    return null;
  }
  const step = line.step;
  const ask = acts.ask;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="quiet"
          size="icon-sm"
          className="size-11 opacity-100 sm:size-7 sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100 sm:data-[state=open]:opacity-100"
          aria-label={`Actions for step ${String(step)} of ${line.provider} ${line.model}`}
          onClick={(event) => {
            // The row behind the button opens the editor on a press; this press is the menu's.
            event.stopPropagation();
          }}
        >
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-52"
        onClick={(event) => {
          // A menu drawn in a portal still bubbles to its row in React's tree.
          event.stopPropagation();
        }}
      >
        <DropdownMenuItem
          onSelect={() => {
            acts.open(line);
          }}
        >
          {EDIT_STEP}
        </DropdownMenuItem>
        {ask === undefined ? null : (
          <>
            {step > 1 ? (
              <DropdownMenuItem
                onSelect={() => {
                  ask({ kind: "move", line, rungId: rung.id, step: step - 1 });
                }}
              >
                <ArrowUp aria-hidden /> {MOVE_UP}
              </DropdownMenuItem>
            ) : null}
            {step < line.of ? (
              <DropdownMenuItem
                onSelect={() => {
                  ask({ kind: "move", line, rungId: rung.id, step: step + 1 });
                }}
              >
                <ArrowDown aria-hidden /> {MOVE_DOWN}
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => {
                ask({ kind: "retire", line, rungId: rung.id });
              }}
            >
              {RETIRE_STEP}
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * A name this short is kept on one line, so a phone breaks the role's words rather than a model's
 * name at its hyphens; a longer one may break anywhere rather than widen the card.
 */
const ONE_LINE_UP_TO = 24;

function oneLine(name: string): string {
  return name.length <= ONE_LINE_UP_TO ? "whitespace-nowrap" : "[overflow-wrap:anywhere]";
}

const HEAD = "h-9 px-2 text-[12px] font-normal text-dim first:pl-3 sm:px-4 sm:first:pl-4";
const CELL = "px-2 py-2 align-middle whitespace-normal first:pl-3 sm:px-4 sm:first:pl-4";

/** The columns of the failover matrix. Which are drawn depends on whether the reader may act on a step. */
function matrixColumns(acts: MatrixActs | undefined): GridColumn<MatrixLine>[] {
  const columns: GridColumn<MatrixLine>[] = [
    {
      id: "complexity",
      header: "Complexity",
      cell: ({ row }) => row.original.level ?? "",
      meta: {
        headerClassName: `${HEAD} hidden sm:table-cell sm:w-[16%]`,
        cellClassName: `${CELL} hidden text-ink sm:table-cell`,
      },
    },
    {
      id: "step",
      header: "Step",
      cell: ({ row }) => (row.original.step === null ? "" : String(row.original.step)),
      meta: { headerClassName: `${HEAD} sm:w-[9%]`, cellClassName: `${CELL} text-acc-text tabular-nums` },
    },
    {
      id: "provider",
      header: "Provider",
      // A level with no step in use says so across the rest of the row, from this column.
      cell: ({ row }) => (row.original.rung === null ? NO_STEP_FOR_THE_LEVEL : row.original.provider),
      meta: {
        headerClassName: `${HEAD} hidden sm:table-cell sm:w-[25%]`,
        cellClassName: `${CELL} hidden text-body [overflow-wrap:anywhere] sm:table-cell`,
      },
    },
    {
      id: "model",
      header: "Model",
      cell: ({ row }) => {
        const line = row.original;
        return (
          <>
            <span className={`block font-mono text-[11.5px] text-ink ${oneLine(line.model)}`}>{line.model}</span>
            {/* A phone has no room for the Provider column, so the provider goes under its model;
                at each width exactly one of the two is displayed, and so read. */}
            <span data-slot="provider-under-model" className={`block text-[11.5px] text-dim sm:hidden ${oneLine(line.provider)}`}>
              {line.provider}
            </span>
          </>
        );
      },
      meta: { headerClassName: `${HEAD} sm:w-[21%]`, cellClassName: CELL },
    },
    {
      id: "role",
      header: "Role",
      cell: ({ row }) => (
        <span className="flex flex-wrap items-center gap-1.5">
          <RolePill role={row.original.role} />
          {row.original.marker === null ? null : <MarkerPill marker={row.original.marker} />}
        </span>
      ),
      meta: { headerClassName: HEAD, cellClassName: CELL },
    },
  ];
  if (acts !== undefined) {
    columns.push({
      id: "actions",
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => <StepMenu line={row.original} acts={acts} />,
      meta: { headerClassName: "h-9 w-14 px-1 sm:w-12", cellClassName: "px-1 py-1 text-right sm:py-0.5" },
    });
  }
  return columns;
}

function MatrixTable({
  lines,
  acts,
  openId,
}: {
  readonly lines: readonly MatrixLine[];
  readonly acts: MatrixActs | undefined;
  readonly openId: string | undefined;
}) {
  const span = acts === undefined ? 3 : 4;
  return (
    <GridTable
      look="kit"
      caption={FAILOVER_MATRIX}
      captionHidden
      className="table-auto text-[13px] sm:table-fixed"
      headClassName="bg-sunk [&_tr]:border-line"
      headRowClassName="hover:bg-transparent"
      columns={matrixColumns(acts)}
      rows={lines}
      rowId={(line) => line.key}
      rowProps={(line) => {
        const rung = line.rung;
        const opens = acts !== undefined && rung !== null;
        return {
          "data-slot": "matrix-row",
          "data-state": rung !== null && rung.id === openId ? "selected" : undefined,
          className: opens ? "group cursor-pointer border-line hover:bg-sunk/60" : "group border-line hover:bg-transparent",
          onClick: opens
            ? () => {
                acts.open(line);
              }
            : undefined,
        };
      }}
      // A level with no step in use has one cell across the rest of its row, so the cells
      // after the first of those are covered and not drawn.
      cellProps={(line, column) => {
        if (line.rung !== null) {
          return undefined;
        }
        if (column === "provider") {
          return { colSpan: span, className: `${CELL} text-dim` };
        }
        return column === "model" || column === "role" || column === "actions" ? { covered: true } : undefined;
      }}
      // A phone has no room for the Complexity column, so a level is named on a row of its
      // own above its first step; at each width exactly one of the two is displayed.
      rowBefore={(line) =>
        line.level === null ? null : (
          <TableRow data-slot="level-row" className="border-line bg-sunk/40 hover:bg-transparent sm:hidden">
            <TableCell colSpan={span} className="px-3 pt-2.5 pb-1.5 text-[12.5px] font-medium text-ink">
              {line.level}
            </TableCell>
          </TableRow>
        )
      }
    />
  );
}

export function FailoverMatrixCard({
  lines,
  acts,
  openId,
  state,
  footer,
}: {
  readonly lines: readonly MatrixLine[];
  /** What a reader who may change the matrix can do with a step. Absent, the rows only read. */
  readonly acts?: MatrixActs | undefined;
  /** The step whose editor is open, drawn as selected. */
  readonly openId?: string | undefined;
  /** Drawn instead of the table while the matrix loads, or when it could not be read. */
  readonly state?: ReactNode | undefined;
  /** Under the table: "Show more" when the API says there is more. */
  readonly footer?: ReactNode | undefined;
}) {
  const headingId = useId();
  return (
    <section
      data-slot="failover-matrix"
      aria-labelledby={headingId}
      className="flex min-w-0 flex-col overflow-hidden rounded-md border border-line bg-panel"
    >
      <div className="flex items-center gap-1 border-b border-line px-4 py-2.5">
        <h2 id={headingId} className="m-0 text-[13.5px] font-semibold text-ink">
          {FAILOVER_MATRIX}
        </h2>
        <AboutTheMatrix />
      </div>
      {state === undefined || state === null ? (
        <MatrixTable lines={lines} acts={acts} openId={openId} />
      ) : (
        <div className="px-4 py-3">{state}</div>
      )}
      {footer === undefined || footer === null ? null : (
        <div className="flex flex-col gap-2 border-t border-line px-4 py-2.5">{footer}</div>
      )}
    </section>
  );
}
