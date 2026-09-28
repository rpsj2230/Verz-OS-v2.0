/**
 * A module's list page: its header, the controls over the list, the table, and "Show more".
 *
 * **Everything a list page repeats is here, so a module writes only what is its own**: which
 * route, which columns, which filters and orders the route declares, and the sentences for its
 * empty and loading states. The states are decided in one order for every module: a failure first,
 * then the first page on its way, then an empty answer, and only then rows.
 *
 * **Two empty sentences and no third.** A list with no search or filter set says what would put a
 * row here; a narrowed list says nothing matches the question, which describes the reader's own
 * question over their own rows (`ListControls.tsx`' `NOTHING_MATCHES`). Neither may say why a list
 * is empty, because "none exist" and "none you may see" are one event to this browser.
 *
 * **No total anywhere.** The page draws rows and whether there are more; see `EntityTable.tsx`.
 *
 * Task ids: M27.10.2, M27.10.3
 */

import type { ReactNode } from "react";
import { FETCHING_MORE, NOTHING_MATCHES, SHOW_MORE } from "../ListControls";
import { narrows, NO_QUESTION, type FilterChoice, type SortChoice } from "../listing";
import type { Listing } from "../useListing";
import { Button } from "../ui/button";
import { EntityTable, type EntityColumn } from "./EntityTable";
import { ListToolbar, RESET_LABEL } from "./ListToolbar";
import { PageHeader, type Crumb } from "./PageHeader";
import { EmptyState, FailureState, LoadingState } from "./states";

/** "Show more" while there is more, and what happened to the last attempt. `ShowMore`'s contract. */
function MoreRows<Row>({ listing }: { readonly listing: Listing<Row> }) {
  return (
    <>
      {listing.moreFailure === null ? null : <FailureState failure={listing.moreFailure} />}
      {listing.fetchingMore ? (
        <p role="status" className="m-0 text-[12.5px] text-dim">
          {FETCHING_MORE}
        </p>
      ) : null}
      {listing.more ? (
        <Button
          variant="outline"
          className="min-h-11 sm:min-h-9"
          disabled={listing.fetchingMore}
          onClick={() => {
            listing.showMore();
          }}
        >
          {SHOW_MORE}
        </Button>
      ) : null}
    </>
  );
}

export interface ListPageProps<Row> {
  readonly crumbs: readonly Crumb[];
  readonly title: string;
  readonly lede?: ReactNode | undefined;
  readonly primary?: ReactNode | undefined;
  readonly actions?: ReactNode | undefined;
  /** Anything between the header and the list, such as a link to a related catalogue. */
  readonly notice?: ReactNode | undefined;
  readonly listing: Listing<Row>;
  /** The rows to draw, read out of `listing.body` by the module's own reader. */
  readonly rows: readonly Row[];
  readonly filtersLabel: string;
  readonly choices?: readonly FilterChoice<Row>[] | undefined;
  readonly sorts?: readonly SortChoice[] | undefined;
  readonly searchHint?: string | undefined;
  readonly caption: string;
  readonly columns: readonly EntityColumn<Row>[];
  readonly rowId: (row: Row) => string;
  readonly rowLabel: (row: Row) => string;
  readonly rowActions?: ((row: Row) => ReactNode) | undefined;
  readonly bulkActions?: ((selected: readonly Row[], clear: () => void) => ReactNode) | undefined;
  readonly exportName?: string | undefined;
  /** Said while the first page is on its way. */
  readonly loading: string;
  /** The empty state of an unnarrowed list: what it is, and what would put a row here. */
  readonly emptyTitle: string;
  readonly emptyDescription: ReactNode;
  readonly emptyAction?: ReactNode | undefined;
  readonly emptyIcon?: ReactNode | undefined;
  /** Drawn under the list: anything the page states about the list as a whole. */
  readonly footer?: ReactNode | undefined;
}

export function ListPage<Row>({
  crumbs,
  title,
  lede,
  primary,
  actions,
  notice,
  listing,
  rows,
  filtersLabel,
  choices,
  sorts,
  searchHint,
  caption,
  columns,
  rowId,
  rowLabel,
  rowActions,
  bulkActions,
  exportName,
  loading,
  emptyTitle,
  emptyDescription,
  emptyAction,
  emptyIcon,
  footer,
}: ListPageProps<Row>) {
  let body: ReactNode;
  if (listing.failure !== null) {
    body = <FailureState failure={listing.failure} />;
  } else if (listing.busy) {
    body = <LoadingState label={loading} />;
  } else if (rows.length === 0) {
    body = narrows(listing.question) ? (
      <EmptyState
        title={NOTHING_MATCHES}
        description="Change the search or clear a filter."
        action={
          <Button
            variant="outline"
            onClick={() => {
              listing.ask({ ...NO_QUESTION, sort: listing.question.sort });
            }}
          >
            {RESET_LABEL}
          </Button>
        }
      />
    ) : (
      <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} icon={emptyIcon} />
    );
  } else {
    body = (
      <EntityTable
        caption={caption}
        columns={columns}
        rows={rows}
        rowId={rowId}
        rowLabel={rowLabel}
        rowActions={rowActions}
        bulkActions={bulkActions}
        exportName={exportName}
      />
    );
  }

  return (
    <div data-slot="list-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={crumbs} title={title} lede={lede} primary={primary} actions={actions} />
      {notice}
      <section aria-label={caption} className="flex min-w-0 flex-col gap-3 rounded-md border border-line bg-panel p-3 sm:p-4">
        <ListToolbar label={filtersLabel} listing={listing} choices={choices} sorts={sorts} searchHint={searchHint} />
        {body}
        <div className="flex flex-wrap items-center gap-2 empty:hidden">
          <MoreRows listing={listing} />
        </div>
      </section>
      {footer}
    </div>
  );
}
