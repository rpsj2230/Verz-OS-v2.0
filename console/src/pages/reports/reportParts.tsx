/**
 * The parts every Report page is built from: its header with the period switch and the export
 * menu, a switch between a few named views, and a list of bars.
 *
 * **Bars are drawn with CSS, not a chart library.** The console mounts no chart library and a
 * report needs one shape, a figure per name, so a bar is a width on a span and the figure beside
 * it is text. The list is a table with a caption and a header per row, so a screen reader hears
 * each name with its figure and never a bar; the bars are `aria-hidden`. A bar is scaled against
 * the largest figure on the same list, which is a row the reader was shown, so the scale carries
 * nothing about rows they were not.
 *
 * **The period is a switch of three, the same on every page**: 7, 30 and 90 days. A closed list
 * rather than a date box, because each report bounds its window on the server and a free box is a
 * second parser of those bounds; the three are inside every route's bound.
 *
 * **Export is what the page shows, as a spreadsheet file.** Each page hands the menu the tables it
 * draws, built with the kit's `toCsv`, so a file holds nothing the reader could not read on the
 * page and a formula character in a value is opened as text.
 *
 * Task ids: M27.16.1
 */

import { Download } from "lucide-react";
import { useState, type ReactNode } from "react";
import { PageHeader, saveCsv, toCsv, type Crumb } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../../components/ui/dropdown-menu";
import { cn } from "../../lib/utils";

/** The periods every Report page offers, in days. Inside every report route's bound. */
export const REPORT_PERIODS = [7, 30, 90] as const;
export type ReportPeriod = (typeof REPORT_PERIODS)[number];

/** What a Report page shows before the reader chooses. */
export const DEFAULT_PERIOD: ReportPeriod = 30;

export const PERIOD_LABEL = "Period";
export const EXPORT_LABEL = "Export";

/** Said on the export control, so nobody reads the file as everything that exists. */
export const EXPORT_HOLDS = "Saves what this page shows you as a spreadsheet file.";

export const SHOW_ALL = "Show all";
export const SHOW_FEWER = "Show fewer";

/** The first crumb of every Report page: the menu group. */
export const REPORTS_CRUMB: Crumb = { label: "Reports" };

/** "Last 30 days", for a sentence or a card's line. */
export function periodWords(days: number): string {
  return `Last ${String(days)} days`;
}

/** One table a page can save: its name in the menu, the file name, and the file's contents. */
export interface Sheet {
  readonly label: string;
  readonly filename: string;
  readonly csv: () => string;
}

/** A sheet of rows in the columns given, each column a heading and the cell as text. */
export function sheetOf<Row>(
  label: string,
  filename: string,
  columns: readonly { readonly header: string; readonly text: (row: Row) => string }[],
  rows: readonly Row[],
): Sheet {
  return {
    label,
    filename,
    csv: () => toCsv(columns.map((one) => ({ id: one.header, header: one.header, cell: one.text, text: one.text })), rows),
  };
}

/** "3 questions", "1 question": a count and its noun, the count in the console's own digits. */
export function counted(count: number, one: string, many: string): string {
  return `${count.toLocaleString("en-GB")} ${count === 1 ? one : many}`;
}

/** A small group of pressed and unpressed buttons: a period, a dimension, an axis. */
export function Switch<Value extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  readonly label: string;
  readonly value: Value;
  readonly options: readonly { readonly value: Value; readonly label: string }[];
  readonly onChange: (value: Value) => void;
}) {
  return (
    <div role="group" aria-label={label} data-slot="report-switch" className="inline-flex flex-wrap rounded-md border border-line bg-panel p-0.5">
      {options.map((one) => (
        <Button
          key={String(one.value)}
          type="button"
          size="sm"
          variant="ghost"
          aria-pressed={one.value === value}
          className="min-h-11 px-2.5 text-dim aria-pressed:bg-sunk aria-pressed:text-ink aria-pressed:font-semibold sm:min-h-7"
          onClick={() => {
            onChange(one.value);
          }}
        >
          {one.label}
        </Button>
      ))}
    </div>
  );
}

/** The period switch, in the words the pages share. */
export function PeriodSwitch({ period, onChange }: { readonly period: ReportPeriod; readonly onChange: (days: ReportPeriod) => void }) {
  return (
    <Switch
      label={PERIOD_LABEL}
      value={period}
      options={REPORT_PERIODS.map((days) => ({ value: days, label: `${String(days)} days` }))}
      onChange={onChange}
    />
  );
}

/** One button for one table, a menu for several, and nothing when the page shows no table. */
export function ExportMenu({ sheets }: { readonly sheets: readonly Sheet[] }) {
  const [first] = sheets;
  if (first === undefined) {
    return null;
  }
  const save = (sheet: Sheet) => {
    saveCsv(`${sheet.filename}.csv`, sheet.csv());
  };
  if (sheets.length === 1) {
    return (
      <Button
        variant="outline"
        size="sm"
        className="min-h-11 sm:min-h-8"
        title={EXPORT_HOLDS}
        onClick={() => {
          save(first);
        }}
      >
        <Download aria-hidden /> {EXPORT_LABEL}
      </Button>
    );
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" title={EXPORT_HOLDS}>
          <Download aria-hidden /> {EXPORT_LABEL}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        {sheets.map((sheet) => (
          <DropdownMenuItem
            key={sheet.filename}
            onSelect={() => {
              save(sheet);
            }}
          >
            {sheet.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The top of a Report page: where it sits, its name, one sentence, the period and the export. */
export function ReportHeader({
  crumbs,
  title,
  lede,
  period,
  onPeriod,
  sheets,
}: {
  readonly crumbs: readonly Crumb[];
  readonly title: string;
  readonly lede: string;
  readonly period: ReportPeriod;
  readonly onPeriod: (days: ReportPeriod) => void;
  readonly sheets: readonly Sheet[];
}) {
  return (
    <PageHeader
      crumbs={crumbs}
      title={title}
      lede={lede}
      actions={
        <>
          <PeriodSwitch period={period} onChange={onPeriod} />
          <ExportMenu sheets={sheets} />
        </>
      }
    />
  );
}

/** One bar: the name it is drawn beside, the figure it scales, and the figure in words. */
export interface Bar {
  readonly key: string;
  readonly label: ReactNode;
  readonly value: number;
  readonly figure: ReactNode;
  /** A second value drawn as a thin line across the bar, such as a target. */
  readonly mark?: number | undefined;
}

/** A bar's width as a share of the largest figure on its list, as a CSS percentage. */
export function barWidth(value: number, largest: number): string {
  if (largest <= 0 || value <= 0) {
    return "0%";
  }
  return `${String(Math.min(100, Math.round((value / largest) * 1000) / 10))}%`;
}

/**
 * Names and figures as a table, with a bar behind each figure. `limit` draws the first rows and a
 * button for the rest, which are rows the reader was sent and are in the export whichever is open.
 */
export function BarList({
  caption,
  keyHeading,
  valueHeading,
  bars,
  limit,
}: {
  readonly caption: string;
  readonly keyHeading: string;
  readonly valueHeading: string;
  readonly bars: readonly Bar[];
  readonly limit?: number | undefined;
}) {
  const [open, setOpen] = useState(false);
  const largest = Math.max(0, ...bars.map((bar) => Math.max(bar.value, bar.mark ?? 0)));
  const cut = limit !== undefined && bars.length > limit;
  const shown = cut && !open ? bars.slice(0, limit) : bars;
  return (
    <div data-slot="bar-list" className="flex min-w-0 flex-col gap-2">
      <table className="w-full table-fixed border-collapse text-[13px]">
        <caption className="sr-only">{caption}</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">{keyHeading}</th>
            <th scope="col">{valueHeading}</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((bar) => (
            <tr key={bar.key} className="border-b border-line last:border-b-0">
              <th scope="row" className="w-[38%] py-2 pr-3 text-left align-middle font-normal text-ink [overflow-wrap:anywhere]">
                {bar.label}
              </th>
              <td className="py-2 align-middle">
                <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                  <span aria-hidden className="relative block h-2 min-w-16 flex-1 overflow-hidden rounded-full bg-sunk">
                    <span className="absolute inset-y-0 left-0 block rounded-full bg-brand" style={{ width: barWidth(bar.value, largest) }} />
                    {bar.mark === undefined ? null : (
                      <span className="absolute inset-y-[-2px] block w-0.5 bg-ink" style={{ left: barWidth(bar.mark, largest) }} />
                    )}
                  </span>
                  <span className="min-w-0 text-right text-[12.5px] text-ink tabular-nums [overflow-wrap:anywhere]">{bar.figure}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {cut ? (
        <div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="min-h-11 text-acc-text sm:min-h-7"
            aria-expanded={open}
            onClick={() => {
              setOpen(!open);
            }}
          >
            {open ? SHOW_FEWER : SHOW_ALL}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/** A short sentence where a card has nothing to draw. Never a figure. */
export function Quiet({ children, className }: { readonly children: ReactNode; readonly className?: string | undefined }) {
  return <p className={cn("m-0 text-[13px] text-dim", className)}>{children}</p>;
}
