/**
 * A person's saved filters: the questions they asked a list that they want to ask again, kept in
 * their own browser under their own identity. No React.
 *
 * **Why the browser and not the API.** A saved filter is a person's own way of looking at a list, not
 * a fact about the company, and the API has no table for it. Writing one would be a new write path,
 * a migration and a row per person per list, to hold a search box and a few dropdown values. Kept
 * here it holds nothing the person could not retype, it is gone when they clear their browser, and
 * it never reaches a server. The cost is that it does not follow them to another machine, which is
 * said on the control. Rejected: keeping them in the address, which would put a person's questions
 * into history and referrer headers, and a shared team view, which would be a list of questions one
 * person asked shown to another, and a question can name something the second person may not see.
 *
 * **Per person, so a shared computer shows nobody else's questions.** The key carries the principal
 * the shell was told by `GET /me`, and the control is not drawn at all when that is unknown, which
 * is the signed-out case and the case of a page mounted outside the shell. The console never reads a
 * token to learn who someone is (`scripts/check-boundaries.mjs`), so the one place that already
 * asks the API who the caller is supplies it (`kit/caller.tsx`).
 *
 * **A saved filter names nothing the person did not type or choose.** What is stored is a name the
 * person wrote, the search words they typed, the values they chose in the dropdowns and the order.
 * Applying one sends that question to the list route exactly as choosing the values by hand would,
 * so the route narrows it over the rows this reader may see: a value that has since become
 * invisible to them matches nothing, which is the answer an absent value gets, and no count of
 * anything is stored or shown. See `A_SAVED_FILTER_ASKS_AGAIN_AND_NEVER_ANSWERS`.
 *
 * **Never a secret, and bounded.** A filter has no field a credential belongs in, the search is cut
 * at the length the routes accept, a list keeps ten, and what is read back is checked field by field,
 * because the browser's storage is a place anything on this origin, or a person with the developer
 * tools open, can write. A malformed entry is dropped and the rest are kept.
 *
 * **Every access can fail and none may throw.** Storage is absent in some private windows, refuses
 * writes when full, and throws on access when site data is blocked. The page works without it: a
 * failed read is no saved filters and a failed write is said to the person.
 *
 * Task ids: M27.16.3
 */

import { NO_QUESTION, type ListQuestion } from "../listing";

export const A_SAVED_FILTER_ASKS_AGAIN_AND_NEVER_ANSWERS =
  "A saved filter stores the question a person asked a list, never what the list answered. Applying " +
  "it asks the route again over the rows this reader may see, so a value that has become invisible to " +
  "them matches nothing, exactly as an absent one does, and nothing stored or shown is a count.";

/** Where the entries live. The version is in the key so a later shape never reads this one's. */
export const STORAGE_PREFIX = "brain-console.saved-filters.v1";

/** The most one person keeps for one list. */
export const MAX_SAVED = 10;
/** The longest name. */
export const MAX_NAME = 60;
/** The longest search: the routes' own limit, which `ListToolbar` also holds. */
export const MAX_SEARCH = 120;

/** One saved question. */
export interface SavedFilter {
  readonly name: string;
  readonly question: ListQuestion;
}

/** The part of the Storage interface this module uses. */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** The browser's storage, or null where it is absent or refuses to be touched. */
export function browserStorage(): StorageLike | null {
  try {
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

/** The key one person's entries for one list are kept under. */
export function keyFor(person: string, list: string): string {
  return `${STORAGE_PREFIX}:${encodeURIComponent(person)}:${encodeURIComponent(list)}`;
}

function textOf(value: unknown, limit: number): string | null {
  return typeof value === "string" && value.length <= limit ? value : null;
}

/** One entry read back strictly, or null for anything that is not exactly the shape written. */
function readEntry(value: unknown): SavedFilter | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const { name, search, filters, sort } = value as Record<string, unknown>;
  const cleanName = textOf(name, MAX_NAME)?.trim();
  const cleanSearch = textOf(search, MAX_SEARCH);
  const cleanSort = textOf(sort, MAX_SEARCH);
  if (cleanName === undefined || cleanName === "" || cleanSearch === null || cleanSort === null) {
    return null;
  }
  if (typeof filters !== "object" || filters === null || Array.isArray(filters)) {
    return null;
  }
  const kept: Record<string, string> = {};
  for (const [column, chosen] of Object.entries(filters)) {
    const columnName = textOf(column, MAX_NAME);
    const chosenValue = textOf(chosen, MAX_SEARCH);
    if (columnName === null || chosenValue === null) {
      return null;
    }
    kept[columnName] = chosenValue;
  }
  return { name: cleanName, question: { search: cleanSearch, filters: kept, sort: cleanSort } };
}

/** What this person has saved for this list, or nothing when storage cannot be read. */
export function readSavedFilters(person: string, list: string, store: StorageLike | null = browserStorage()): SavedFilter[] {
  if (store === null) {
    return [];
  }
  try {
    const raw = store.getItem(keyFor(person, list));
    if (raw === null) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.map(readEntry).filter((one): one is SavedFilter => one !== null).slice(0, MAX_SAVED);
  } catch {
    return [];
  }
}

function write(person: string, list: string, entries: readonly SavedFilter[], store: StorageLike | null): boolean {
  if (store === null) {
    return false;
  }
  try {
    store.setItem(
      keyFor(person, list),
      JSON.stringify(
        entries.map((one) => ({
          name: one.name,
          search: one.question.search,
          filters: one.question.filters,
          sort: one.question.sort,
        })),
      ),
    );
    return true;
  } catch {
    return false;
  }
}

export type SaveOutcome =
  | { readonly saved: true; readonly filters: SavedFilter[] }
  | { readonly saved: false; readonly why: "no-name" | "nothing-to-save" | "full" | "unavailable"; readonly filters: SavedFilter[] };

/** Whether a question holds anything worth keeping: words or at least one chosen value. */
export function holdsAQuestion(question: ListQuestion): boolean {
  return question.search.trim() !== "" || Object.values(question.filters).some((value) => value !== "");
}

/**
 * Keep `question` under `name`. A name already kept is replaced, so saving again is how a filter is
 * changed, and an eleventh is refused rather than dropping one the person chose to keep.
 */
export function saveFilter(
  person: string,
  list: string,
  name: string,
  question: ListQuestion,
  store: StorageLike | null = browserStorage(),
): SaveOutcome {
  const current = readSavedFilters(person, list, store);
  const clean = name.trim().slice(0, MAX_NAME);
  if (clean === "") {
    return { saved: false, why: "no-name", filters: current };
  }
  if (!holdsAQuestion(question)) {
    return { saved: false, why: "nothing-to-save", filters: current };
  }
  const replacing = current.some((one) => one.name === clean);
  if (!replacing && current.length >= MAX_SAVED) {
    return { saved: false, why: "full", filters: current };
  }
  const entry: SavedFilter = {
    name: clean,
    question: {
      search: question.search.trim().slice(0, MAX_SEARCH),
      filters: Object.fromEntries(Object.entries(question.filters).filter(([, value]) => value !== "")),
      sort: question.sort,
    },
  };
  const next = replacing ? current.map((one) => (one.name === clean ? entry : one)) : [...current, entry];
  return write(person, list, next, store) ? { saved: true, filters: next } : { saved: false, why: "unavailable", filters: current };
}

/** Drop the entry called `name`. Dropping one that is not there changes nothing. */
export function forgetFilter(person: string, list: string, name: string, store: StorageLike | null = browserStorage()): SavedFilter[] {
  const current = readSavedFilters(person, list, store);
  const next = current.filter((one) => one.name !== name);
  if (next.length === current.length) {
    return current;
  }
  return write(person, list, next, store) ? next : current;
}

/**
 * A saved question cut to what this list offers today: filters on columns it filters, an order it
 * offers. A column or order the list no longer has is dropped rather than sent, so a saved filter
 * from before a page changed asks nothing the route would not take.
 */
export function fitToList(saved: SavedFilter, columns: readonly string[], sorts: readonly string[]): ListQuestion {
  return {
    ...NO_QUESTION,
    search: saved.question.search,
    filters: Object.fromEntries(Object.entries(saved.question.filters).filter(([column]) => columns.includes(column))),
    sort: sorts.includes(saved.question.sort) ? saved.question.sort : "",
  };
}

/** The address parameters a list that keeps its question in the address spells each part with. */
export interface AddressNames {
  /** The parameter the search words travel in. */
  readonly search: string;
  /** Column to parameter. */
  readonly filters: Readonly<Record<string, string>>;
  /** The parameter the order travels in. */
  readonly sort: string;
  /** Parameters that are a position in the old question and must not outlive it, such as a cursor. */
  readonly reset?: readonly string[] | undefined;
}

/**
 * The address that asks `question` of a list whose state lives in its address, keeping whatever else
 * the address carries (such as the subject a history is of) and dropping the parameters of the question
 * it replaces. Empty parts are left out, so one question is one address.
 */
export function addressFor(base: string, question: ListQuestion, names: AddressNames, current: URLSearchParams): string {
  const next = new URLSearchParams(current);
  for (const name of [names.search, names.sort, ...Object.values(names.filters), ...(names.reset ?? [])]) {
    next.delete(name);
  }
  if (question.search !== "") {
    next.set(names.search, question.search);
  }
  if (question.sort !== "") {
    next.set(names.sort, question.sort);
  }
  for (const [column, name] of Object.entries(names.filters)) {
    const chosen = question.filters[column] ?? "";
    if (chosen !== "") {
      next.set(name, chosen);
    }
  }
  const query = next.toString();
  return query === "" ? base : `${base}?${query}`;
}
