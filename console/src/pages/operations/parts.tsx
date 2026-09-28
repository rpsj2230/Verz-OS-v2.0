/**
 * The parts the Operations pages share on top of the page kit: a frame for a screen answered by one
 * read, a table section for a list answered whole, a pill for a state word, and the words for a
 * job's name and a length of time.
 *
 * **A list answered whole has no search, filter or pager, because its route takes none.** Jobs,
 * live runs, failures, buckets, windows and connections are each one bounded answer,
 * and `kit/ListPage` draws a search box that a route ignoring it would answer with every row: a
 * control that reaches nothing. So these sections are `kit/EntityTable` inside a `kit/SectionCard`,
 * with its column choice and its export of the rows shown, and nothing else.
 *
 * **A job is named in words, and its identifier is in Advanced.** `spend_report_refresh` is how the
 * registry names a control; "Spend report refresh" is how a person reads it. The words are made from
 * the identifier by one rule, so two jobs can never be shown under the same name.
 *
 * Task ids: M27.16.1, M27.10.2
 */

import type { ReactNode } from "react";
import type { ApiFailure } from "../../api/errors";
import {
  EmptyState,
  EntityTable,
  FailureState,
  LoadingState,
  PageHeader,
  SectionCard,
  type Crumb,
  type EntityColumn,
} from "../../components/kit";

/** What a page says when the API answered in a shape this console does not read. */
export const UNREADABLE =
  "The answer came back in a shape this console does not read. The console and the API are probably from different releases.";

/** The menu groups these pages sit in, which are the first step of each trail. */
export const OPERATIONS = "Operations";
export const PLATFORM = "Platform";
export const GOVERNANCE = "Governance";
export const KNOWLEDGE = "Knowledge and data";

/** A registry identifier as a person reads it: underscores as spaces, the first letter capital. */
export function jobName(control: string): string {
  const words = control.replace(/_/g, " ").trim();
  return words === "" ? control : `${words.slice(0, 1).toLocaleUpperCase("en-GB")}${words.slice(1)}`;
}

/**
 * A length of time in words, to the two largest units that are not zero. Under a minute is said as
 * that, since a run's age is read to decide whether to worry and seconds invite a false precision.
 */
export function durationWords(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  if (whole < 60) {
    return "under a minute";
  }
  const units: readonly (readonly [string, number])[] = [
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  const parts: string[] = [];
  let left = whole;
  for (const [name, size] of units) {
    const count = Math.floor(left / size);
    left -= count * size;
    if (count > 0 && parts.length < 2) {
      parts.push(`${String(count)} ${name}${count === 1 ? "" : "s"}`);
    }
  }
  return parts.join(" ");
}

/** An instant as a day and a time in the reader's own zone, or the value itself when it is not one. */
export function at(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

/** A sentence under a card, in the dim register. */
export function Line({ children }: { readonly children: ReactNode }) {
  return <p className="m-0 text-[12.5px] leading-snug text-dim">{children}</p>;
}

/**
 * A page answered by one read: its header, then its failure, its loading state, a sentence when the
 * answer is unreadable, or its body.
 */
export function OpsPage<Body>({
  crumbs,
  title,
  lede,
  primary,
  actions,
  notice,
  loading,
  busy,
  failure,
  body,
  children,
}: {
  readonly crumbs: readonly Crumb[];
  readonly title: string;
  readonly lede?: ReactNode | undefined;
  readonly primary?: ReactNode | undefined;
  readonly actions?: ReactNode | undefined;
  /** Drawn under the header whatever state the read is in, such as what an act just did. */
  readonly notice?: ReactNode | undefined;
  /** Said while the answer is on its way. */
  readonly loading: string;
  readonly busy: boolean;
  readonly failure: ApiFailure | null;
  /** The answer read, or null when it came back unreadable. */
  readonly body: Body | null;
  readonly children: (body: Body) => ReactNode;
}) {
  let content: ReactNode;
  if (failure !== null) {
    content = <FailureState failure={failure} />;
  } else if (busy) {
    content = <LoadingState label={loading} />;
  } else if (body === null) {
    content = <p className="m-0 text-sm text-dim">{UNREADABLE}</p>;
  } else {
    content = children(body);
  }
  return (
    <div data-slot="ops-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={crumbs} title={title} lede={lede} primary={primary} actions={actions} />
      {notice}
      {content}
    </div>
  );
}

/** A list answered whole, in a headed card: the table, or one sentence saying there is nothing. */
export function WholeList<Row>({
  title,
  lede,
  action,
  caption,
  columns,
  rows,
  rowId,
  rowLabel,
  rowActions,
  exportName,
  empty,
  emptyDescription,
  footer,
}: {
  readonly title: string;
  readonly lede?: ReactNode | undefined;
  readonly action?: ReactNode | undefined;
  readonly caption: string;
  readonly columns: readonly EntityColumn<Row>[];
  readonly rows: readonly Row[];
  readonly rowId: (row: Row) => string;
  readonly rowLabel: (row: Row) => string;
  readonly rowActions?: ((row: Row) => ReactNode) | undefined;
  readonly exportName?: string | undefined;
  /** The empty sentence, whichever reason the list is empty for. */
  readonly empty: string;
  readonly emptyDescription?: ReactNode | undefined;
  readonly footer?: ReactNode | undefined;
}) {
  return (
    <SectionCard title={title} lede={lede} action={action} footer={footer}>
      {rows.length === 0 ? (
        <EmptyState title={empty} description={emptyDescription ?? ""} />
      ) : (
        <EntityTable
          caption={caption}
          columns={columns}
          rows={rows}
          rowId={rowId}
          rowLabel={rowLabel}
          rowActions={rowActions}
          exportName={exportName}
        />
      )}
    </SectionCard>
  );
}
