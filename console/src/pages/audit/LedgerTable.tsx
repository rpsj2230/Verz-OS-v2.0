/**
 * The ledger's rows as a table, and the control that fetches older ones. Shared by the Audit log and
 * a subject's own page, which draw the same entries narrowed differently.
 *
 * **Who, what and about, in words.** A row reads as a person's name, what the entry records
 * (`auditWords.whatWords`) and what it is about, which links to that subject's page. Identifiers are
 * on the subject's page, in Advanced, and never in a cell.
 *
 * **No total and no "end of the ledger".** The table draws the rows the API sent and whether there
 * is a cursor; `EntityTable` and this component carry no count, for `auditQuery.ts`' reason.
 *
 * Task ids: M27.7.13, M27.16.1
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { EntityTable, FailureState, type EntityColumn } from "../../components/kit";
import { FETCHING_MORE } from "../../components/ListControls";
import { Button } from "../../components/ui/button";
import { subjectAddress, when, type AuditRow } from "../auditQuery";
import { actorWords, detailLines, subjectWords, whatWords } from "./auditWords";
import type { Ledger } from "./useLedger";

/** One row with its place in the walk, which is its key: two entries may share an instant. */
interface Placed {
  readonly row: AuditRow;
  readonly at: number;
}

export const WHEN_COLUMN = "When";
export const WHO_COLUMN = "Who";
export const WHAT_COLUMN = "What";
export const ABOUT_COLUMN = "About";
export const DETAILS_COLUMN = "Details";

function Details({ lines }: { readonly lines: readonly string[] }) {
  if (lines.length === 0) {
    return null;
  }
  return (
    <ul className="m-0 flex list-none flex-col gap-0.5 p-0 text-[12px] text-dim [overflow-wrap:anywhere]">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

export function LedgerTable({
  ledger,
  caption,
  exportName,
  showAbout = true,
  whoCell,
  moreLabel,
}: {
  readonly ledger: Ledger;
  readonly caption: string;
  readonly exportName: string;
  /** False on a subject's own page, where every row is about the same thing. */
  readonly showAbout?: boolean | undefined;
  /** How a person is drawn, when the page links them somewhere; their name otherwise. */
  readonly whoCell?: ((row: AuditRow, name: string) => ReactNode) | undefined;
  readonly moreLabel: string;
}) {
  const people = ledger.people;
  const placed: readonly Placed[] = ledger.rows.map((row, at) => ({ row, at }));
  const columns: EntityColumn<Placed>[] = [
    {
      id: "when",
      header: WHEN_COLUMN,
      hideable: false,
      className: "whitespace-nowrap",
      cell: ({ row }) => <time dateTime={row.at}>{when(row.at)}</time>,
      text: ({ row }) => row.at,
    },
    {
      id: "who",
      header: WHO_COLUMN,
      cell: ({ row }) => {
        const name = actorWords(row.actor_id, people, row.details);
        return whoCell === undefined ? name : whoCell(row, name);
      },
      text: ({ row }) => actorWords(row.actor_id, people, row.details),
    },
    {
      id: "what",
      header: WHAT_COLUMN,
      cell: ({ row }) => <span className="font-medium text-ink">{whatWords(row.action, row.details)}</span>,
      text: ({ row }) => whatWords(row.action, row.details),
    },
    ...(showAbout
      ? [
          {
            id: "about",
            header: ABOUT_COLUMN,
            cell: ({ row }: Placed) => (
              <Link
                to={subjectAddress(row.subject_kind, row.subject_id)}
                className="text-ink underline-offset-4 hover:text-acc-text hover:underline"
              >
                {subjectWords(row.subject_kind, row.subject_id, people)}
              </Link>
            ),
            text: ({ row }: Placed) => subjectWords(row.subject_kind, row.subject_id, people),
          },
        ]
      : []),
    {
      id: "details",
      header: DETAILS_COLUMN,
      cell: ({ row }) => <Details lines={detailLines(row.details)} />,
      text: ({ row }) => detailLines(row.details).join("; "),
    },
  ];

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <EntityTable
        caption={caption}
        columns={columns}
        rows={placed}
        rowId={(one) => String(one.at)}
        rowLabel={(one) => `${whatWords(one.row.action, one.row.details)}, ${when(one.row.at)}`}
        exportName={exportName}
      />
      {ledger.moreFailure === null ? null : <FailureState failure={ledger.moreFailure} />}
      {ledger.fetchingMore ? (
        <p role="status" className="m-0 text-[12.5px] text-dim">
          {FETCHING_MORE}
        </p>
      ) : null}
      {ledger.more ? (
        <div>
          <Button variant="outline" className="min-h-11 sm:min-h-9" disabled={ledger.fetchingMore} onClick={ledger.showMore}>
            {moreLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
