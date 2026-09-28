/**
 * The controls over a module list: a search box, a filter per offered column, an order, and a way
 * back to everything. `ListControls.tsx`' contract drawn in the component layer's style.
 *
 * **The same contract, reused rather than restated.** It takes the `Listing` that `useListing`
 * returns and the `FilterChoice` and `SortChoice` a page already declares, and every control changes
 * the question asked of the API and touches no row, which is `ListControls.tsx`' rule and the
 * server list contract's (`brain.listing`). A filter offers only `offered`, the values on rows the
 * reader was already shown, plus whatever is chosen now so the control can say what it is set to.
 * See `listing.ts`' `A_FILTER_OFFERS_ONLY_WHAT_WAS_SHOWN`.
 *
 * **Native selects, deliberately.** A filter and an order are a choice from a short list, and the
 * platform's own select is keyboard-complete, opens the phone's own picker, and needs no portal. The
 * Radix select is kept for forms whose options need more than a line of text each.
 *
 * **Drawn whatever state the list is in**, so the box somebody is typing in is never unmounted by
 * the loading state that typing started.
 *
 * Task ids: M27.10.2, M27.10.3
 */

import { Search, X } from "lucide-react";
import { useId, type ReactNode } from "react";
import { cn } from "../../lib/utils";
import { NO_QUESTION, narrows, type FilterChoice, type ListQuestion, type SortChoice } from "../listing";
import { SEARCH_LABEL, SORT_LABEL } from "../ListControls";
import type { Listing } from "../useListing";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

export const RESET_LABEL = "Clear search and filters";

/** The longest search the list routes accept; `ListControls.tsx` holds the same. */
const SEARCH_LIMIT = 120;

const SELECT =
  "h-11 min-w-0 max-w-full rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring sm:h-8";

function Choice({
  label,
  value,
  onChange,
  children,
}: {
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly children: ReactNode;
}) {
  const id = useId();
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <label htmlFor={id} className="text-[12.5px] whitespace-nowrap text-dim">
        {label}
      </label>
      <select
        id={id}
        className={SELECT}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        {children}
      </select>
    </span>
  );
}

export function ListToolbar<Row>({
  label,
  listing,
  choices = [],
  sorts = [],
  searchHint,
  className,
}: {
  /** What the controls narrow, for a screen reader: "Narrow the agents". */
  readonly label: string;
  readonly listing: Listing<Row>;
  readonly choices?: readonly FilterChoice<Row>[] | undefined;
  readonly sorts?: readonly SortChoice[] | undefined;
  readonly searchHint?: string | undefined;
  readonly className?: string | undefined;
}) {
  const { question, ask, offered } = listing;
  const searchId = useId();
  const set = (next: Partial<ListQuestion>) => {
    ask({ ...question, ...next });
  };

  return (
    <form
      data-slot="list-toolbar"
      role="search"
      aria-label={label}
      className={cn("flex min-w-0 flex-wrap items-center gap-2", className)}
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <span className="relative flex w-full min-w-0 items-center sm:w-64">
        <label htmlFor={searchId} className="sr-only">
          {SEARCH_LABEL}
        </label>
        <Search aria-hidden className="pointer-events-none absolute left-2.5 size-4 text-dim" />
        <Input
          id={searchId}
          type="search"
          className="h-11 pl-8 sm:h-8"
          value={question.search}
          maxLength={SEARCH_LIMIT}
          placeholder={searchHint}
          onChange={(event) => {
            set({ search: event.target.value });
          }}
        />
      </span>
      {choices.map((choice) => {
        const chosen = question.filters[choice.column] ?? "";
        const values = offered[choice.column] ?? [];
        const shown = chosen === "" || values.includes(chosen) ? values : [...values, chosen];
        return (
          <Choice
            key={choice.column}
            label={choice.label}
            value={chosen}
            onChange={(value) => {
              set({ filters: { ...question.filters, [choice.column]: value } });
            }}
          >
            <option value="">{choice.everything}</option>
            {shown.map((value) => (
              <option key={value} value={value}>
                {choice.describe === undefined ? value : choice.describe(value)}
              </option>
            ))}
          </Choice>
        );
      })}
      {sorts.length === 0 ? null : (
        <Choice
          label={SORT_LABEL}
          value={question.sort}
          onChange={(value) => {
            set({ sort: value });
          }}
        >
          {sorts.map((one) => (
            <option key={one.value} value={one.value}>
              {one.label}
            </option>
          ))}
        </Choice>
      )}
      {narrows(question) ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="min-h-11 sm:min-h-8"
          onClick={() => {
            ask({ ...NO_QUESTION, sort: question.sort });
          }}
        >
          {RESET_LABEL} <X aria-hidden />
        </Button>
      ) : null}
    </form>
  );
}
