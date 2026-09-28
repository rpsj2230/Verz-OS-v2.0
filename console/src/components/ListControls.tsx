/**
 * The controls over a long list: a search box, a filter per offered column, an order, and "Show
 * more". Every one of them changes the question asked of the API; none of them touches a row.
 *
 * **Drawn whatever state the list is in.** A page that swapped the controls for "Loading." while a
 * search was answered would unmount the box somebody is typing in, and the next key would go
 * nowhere. So a page draws these once and puts its own loading, empty and failed sentences under
 * them.
 *
 * **A filter's options are `useListing`'s `offered`**, the values on rows already drawn, and a
 * value that is currently chosen is kept in the list whatever happened, so the control can always
 * say what it is set to. See `listing.ts`' `A_FILTER_OFFERS_ONLY_WHAT_WAS_SHOWN`.
 *
 * **The empty sentence under a narrowed list is about the question, not the company.** "Nothing
 * here matches that" is said only when a search or a filter is set, and it describes the reader's
 * own rows: the search ran over what they may see.
 *
 * Task ids: M27.8.6
 */

import type { ChangeEvent } from "react";
import { FailureNotice } from "../ui/FailureNotice";
import type { FilterChoice, ListQuestion, SortChoice } from "./listing";
import type { Listing } from "./useListing";

export const SEARCH_LABEL = "Search";
export const SORT_LABEL = "Sort by";
export const SHOW_MORE = "Show more";
export const FETCHING_MORE = "Fetching more.";

/** What a narrowed list with no rows says. About the question, never about what exists. */
export const NOTHING_MATCHES = "Nothing here matches that search or filter.";

interface ListControlsProps<Row> {
  /** What the controls narrow, for a screen reader: "Narrow the sessions". */
  readonly label: string;
  readonly listing: Listing<Row>;
  readonly choices?: readonly FilterChoice<Row>[];
  readonly sorts?: readonly SortChoice[];
  /** A hint in the search box saying what it reads. */
  readonly searchHint?: string;
}

export function ListControls<Row>({
  label,
  listing,
  choices = [],
  sorts = [],
  searchHint,
}: ListControlsProps<Row>) {
  const { question, ask, offered } = listing;
  // Each control is inside its label and also named by it through `htmlFor` and an id, with a
  // `name`: an audit on the owner's install on 2026-09-28 read these controls as unnamed, and a
  // label that both wraps and points leaves no tool a way to miss the association. The ids are
  // made from the form's own label rather than `useId`, so two mounts of one screen draw the same
  // markup, which several tests compare byte for byte.
  const ids = `list-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  const set = (next: Partial<ListQuestion>) => {
    ask({ ...question, ...next });
  };
  const filter = (column: string) => (event: ChangeEvent<HTMLSelectElement>) => {
    set({ filters: { ...question.filters, [column]: event.target.value } });
  };

  return (
    <form
      className="form list-controls"
      role="search"
      aria-label={label}
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <label className="control-label" htmlFor={`${ids}-search`}>
        {SEARCH_LABEL}{" "}
        <input
          id={`${ids}-search`}
          name="search"
          type="search"
          className="form-control"
          value={question.search}
          maxLength={120}
          placeholder={searchHint}
          onChange={(event) => {
            set({ search: event.target.value });
          }}
        />
      </label>
      {choices.map((choice) => {
        const chosen = question.filters[choice.column] ?? "";
        const values = offered[choice.column] ?? [];
        const shown = chosen === "" || values.includes(chosen) ? values : [...values, chosen];
        return (
          <label key={choice.column} className="control-label" htmlFor={`${ids}-filter-${choice.column}`}>
            {choice.label}{" "}
            <select
              id={`${ids}-filter-${choice.column}`}
              name={choice.column}
              className="form-control"
              value={chosen}
              onChange={filter(choice.column)}
            >
              <option value="">{choice.everything}</option>
              {shown.map((value) => (
                <option key={value} value={value}>
                  {choice.describe === undefined ? value : choice.describe(value)}
                </option>
              ))}
            </select>
          </label>
        );
      })}
      {sorts.length === 0 ? null : (
        <label className="control-label" htmlFor={`${ids}-sort`}>
          {SORT_LABEL}{" "}
          <select
            id={`${ids}-sort`}
            name="sort"
            className="form-control"
            value={question.sort}
            onChange={(event) => {
              set({ sort: event.target.value });
            }}
          >
            {sorts.map((one) => (
              <option key={one.value} value={one.value}>
                {one.label}
              </option>
            ))}
          </select>
        </label>
      )}
    </form>
  );
}

/** "Show more", while there is more, and what happened to the last attempt. */
export function ShowMore<Row>({ listing }: { readonly listing: Listing<Row> }) {
  return (
    <>
      {listing.moreFailure === null ? null : <FailureNotice failure={listing.moreFailure} />}
      {listing.fetchingMore ? (
        <p className="note" role="status">
          {FETCHING_MORE}
        </p>
      ) : null}
      {listing.more ? (
        <button
          type="button"
          className="button"
          disabled={listing.fetchingMore}
          onClick={() => {
            listing.showMore();
          }}
        >
          {SHOW_MORE}
        </button>
      ) : null}
    </>
  );
}
