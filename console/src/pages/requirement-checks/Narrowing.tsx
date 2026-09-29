/**
 * The controls over a list answered whole: a search box, a choice per column, and a way back to
 * everything. `kit/ListToolbar` drawn for a route that takes no search or filter.
 *
 * **Only for an answer that is the whole list.** `kit/ListToolbar` asks the API, because a paged
 * list narrowed in the browser narrows only the rows that arrived and looks identical to the
 * server's answer. The pages that use this read one bounded answer that is the whole list for this
 * reader (one area of the register, one learning review, one person's memory), so narrowing it here
 * narrows everything they were sent and nothing they were not.
 *
 * **Native selects**, for `kit/ListToolbar`'s reason: keyboard-complete, the phone's own picker, and
 * no portal.
 *
 * Task ids: M27.16.1
 */

import { Search, X } from "lucide-react";
import { useId, type ReactNode } from "react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { RESET_LABEL } from "../../components/kit";

const SELECT =
  "h-11 min-w-0 max-w-full rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring sm:h-8";

/** One choice over a column: its label, what "everything" reads as, and the values offered. */
export interface Narrow {
  readonly label: string;
  readonly everything: string;
  readonly value: string;
  readonly options: readonly { readonly value: string; readonly label: string }[];
  readonly onChange: (value: string) => void;
}

function Choice({ narrow }: { readonly narrow: Narrow }) {
  const id = useId();
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <label htmlFor={id} className="text-[12.5px] whitespace-nowrap text-dim">
        {narrow.label}
      </label>
      <select
        id={id}
        className={SELECT}
        value={narrow.value}
        onChange={(event) => {
          narrow.onChange(event.target.value);
        }}
      >
        {narrow.everything === "" ? null : <option value="">{narrow.everything}</option>}
        {narrow.options.map((one) => (
          <option key={one.value} value={one.value}>
            {one.label}
          </option>
        ))}
      </select>
    </span>
  );
}

export function Narrowing({
  label,
  search,
  onSearch,
  searchLabel,
  searchHint,
  narrows = [],
  onReset,
  children,
}: {
  /** What the controls narrow, for a screen reader. */
  readonly label: string;
  readonly search?: string | undefined;
  readonly onSearch?: ((value: string) => void) | undefined;
  readonly searchLabel?: string | undefined;
  readonly searchHint?: string | undefined;
  readonly narrows?: readonly Narrow[] | undefined;
  /** Clears the search and every choice; drawn only while something is narrowed. */
  readonly onReset?: (() => void) | undefined;
  /** Anything else beside the controls, such as a choice that is not a narrowing. */
  readonly children?: ReactNode | undefined;
}) {
  const searchId = useId();
  const narrowed = (search ?? "") !== "" || narrows.some((one) => one.value !== "" && one.everything !== "");
  return (
    <form
      data-slot="narrowing"
      role="search"
      aria-label={label}
      className="flex min-w-0 flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      {children}
      {onSearch === undefined ? null : (
        <span className="relative flex w-full min-w-0 items-center sm:w-64">
          <label htmlFor={searchId} className="sr-only">
            {searchLabel ?? "Search"}
          </label>
          <Search aria-hidden className="pointer-events-none absolute left-2.5 size-4 text-dim" />
          <Input
            id={searchId}
            type="search"
            className="h-11 pl-8 sm:h-8"
            value={search ?? ""}
            maxLength={120}
            placeholder={searchHint}
            onChange={(event) => {
              onSearch(event.target.value);
            }}
          />
        </span>
      )}
      {narrows.map((one) => (
        <Choice key={one.label} narrow={one} />
      ))}
      {narrowed && onReset !== undefined ? (
        <Button type="button" variant="ghost" size="sm" className="min-h-11 sm:min-h-8" onClick={onReset}>
          {RESET_LABEL} <X aria-hidden />
        </Button>
      ) : null}
    </form>
  );
}
