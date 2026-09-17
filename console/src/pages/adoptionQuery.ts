/**
 * What the adoption screen asks the API for, and how a page of lines is read. No React.
 *
 * `brain.console.adoption_view` narrows the departments through the same predicate the usage
 * report is read behind, and `brain.adoption.adoption_by_department` gives every reachable
 * department a line, zero included. Both facts decide what this module may do with the page it
 * is handed, and the second is the surprising one: a line whose figures are zero is a real
 * answer and must be drawn, because a page that dropped it would say which departments have
 * been quiet. See `A_ZERO_IS_A_LINE_AND_NOT_AN_ABSENCE`.
 *
 * **Nothing is sorted, totalled or counted here.** The lines arrive in department order, they
 * are drawn in the order they arrived, and there is no sum over them: an adoption line is a
 * department's own two figures and the answer holds no total, so a total drawn here would be
 * the one figure on the screen the API does not stand behind.
 *
 * **`truncated` is a flag and there is no count anywhere.** It says the page came back full,
 * which is a fact with no arithmetic in it, and it is the same shape `matrixQuery.ts` reads for
 * the matrix. `total` is inherited by the response model and never populated, and it stops
 * here: this module has no field for it and therefore no path from the payload to a renderer.
 *
 * Task ids: M27.7.17, M27.8.6
 */

import type { components } from "../api/schema";
import type { FilterChoice, SortChoice } from "../components/listing";

/** One department's adoption, as `brain.report_routes.AdoptionLineView` sends it. */
export type AdoptionLineRow = components["schemas"]["AdoptionLineView"];

/** Written down because dropping the zero rows is what a person does to tidy a table. */
export const A_ZERO_IS_A_LINE_AND_NOT_AN_ABSENCE =
  "brain.adoption.adoption_by_department gives every department in the reader's reach a line, " +
  "zero included, so that whether a line appears is a fact about the reader's reach and never " +
  "about what happened. A console that hid the zero rows would undo that in one filter: the " +
  "departments left on the page would be exactly the ones with traffic, and a reader would " +
  "learn which of the departments they may see has stopped using the system from a screen " +
  "that was careful not to tell them.";

/** Where the API keeps the adoption page. */
export const ADOPTION_API_PATH = "/report/adoption";

/** The console address for this screen. */
export const ADOPTION_PATH = "/adoption";

/** The two parameters the route declares. */
export const DAYS_PARAMETER = "days";
export const LIMIT_PARAMETER = "limit";

/**
 * How long a window this screen asks for.
 *
 * Thirty days, which is the route's own default and the shortest window in which "who has
 * stopped" means anything. Well below `MAX_ADOPTION_DAYS`, so no load is refused with a
 * validation error.
 */
export const ADOPTION_DAYS = 30;

/** The windows a reader may choose, in days. A closed list: a free number box is a second parser. */
export const ADOPTION_PERIODS: readonly number[] = [7, ADOPTION_DAYS, 90, 365];

export function periodWords(days: number): string {
  return days === 365 ? "The last year" : `The last ${String(days)} days`;
}

/** The filters the adoption route declares that this screen offers, over lines drawn. */
export const ADOPTION_FILTERS: readonly FilterChoice<AdoptionLineRow>[] = [
  { column: "department", label: "Department", everything: "All departments", read: (row) => row.department },
];

export const ADOPTION_SORTS: readonly SortChoice[] = [
  { value: "", label: "By department" },
  { value: "-questions", label: "Most questions first" },
  { value: "-people", label: "Most people first" },
];

/** One page of adoption, as this console holds it. Two fields, deliberately. */
export interface AdoptionPage {
  readonly lines: readonly AdoptionLineRow[];
  /** The page came back full. Never how much more there is. */
  readonly truncated: boolean;
}

const NOTHING: AdoptionPage = Object.freeze({ lines: [], truncated: false });

/**
 * Read a page of adoption out of a response body.
 *
 * **`total` stops here**, in the way `readMatrixPage` drops it: not an agreement not to render
 * it, but no field to render. `AdoptionPage` inherits `total` from `brain.api.Page` and never
 * populates it, and a console holding the field is a console one line away from showing it.
 *
 * An unreadable body yields an empty page rather than null, which is the opposite of what the
 * two report screens beside this one do, and the difference is what an empty page means here.
 * A page with no lines is what a reader with no usage grant is answered, so it is already a
 * shape this screen has to draw honestly, and it says exactly what a malformed body should
 * say: there is nothing to show.
 */
export function readAdoptionPage(payload: unknown): AdoptionPage {
  if (typeof payload !== "object" || payload === null) {
    return NOTHING;
  }
  const body = payload as { items?: unknown; truncated?: unknown };
  if (!Array.isArray(body.items)) {
    return NOTHING;
  }
  return {
    lines: body.items as AdoptionLineRow[],
    truncated: body.truncated === true,
  };
}
