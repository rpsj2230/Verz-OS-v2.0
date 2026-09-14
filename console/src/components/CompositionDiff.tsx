/**
 * One agent beside the template it came from, path by path, both sides at once (M39.1.1.5).
 *
 * **The rows are `brain.console.workspace.composition_rows`'s and the arrangement is
 * `PART_OF_PATH`'s.** An earlier version of this comment said the rows were
 * `brain.agents.upgrade`'s, and they could not be: `upgrade` diffs a pinned version against a
 * newer candidate and returns only the paths that moved. `composition_rows` compares an
 * instance with the template it came from and emits exactly the wire names read here. No
 * route serves them yet, so the diff is rendered from whatever an answer carries, which
 * today is nothing.
 *
 * **Divergence is read off the row and never off the two columns**, which is the one place
 * a diff in a browser goes wrong quietly. See
 * `DIVERGENCE_IS_READ_FROM_THE_OVERLAY_AND_NEVER_FROM_TWO_VALUES`: `brain.agents.upgrade`
 * states that a path where both answers coincide is still a conflict, so a row whose two
 * columns are identical can still be a value somebody set on this agent, and a console that
 * compared the columns would render it as untouched. It would be right on every other row,
 * which is what makes it survive review.
 *
 * **A path whose value the reader may not see is not a row.** There is no cell that could
 * hold a lock, no "changed" marker without a value beside it, and nothing anywhere counts
 * what did not arrive. See `A_DIFF_ROW_CARRIES_BOTH_SIDES_OR_IT_IS_NOT_A_ROW`. An empty
 * diff and a diff every row of which was withheld are one screen and one sentence.
 *
 * **The caption does not name the template.** It says what the table is without saying what
 * this agent came from, because a reader who may not be told the lineage may still be shown
 * the paths, and a caption is exactly where that fact would leak back in through the
 * furniture.
 *
 * **The word in the source column is the API's own**, as `src/ui/Status.tsx` renders a state
 * word. Only one of them changes what this table draws, and a word neither the Python enum
 * nor this console knows is drawn as itself and marks nothing: inventing "set here" for an
 * unrecognised word would mark a row as locally edited on no evidence at all.
 *
 * Task ids: M39.1.1.5
 */

import { Chip } from "../ui/Chip";
import type { DiffRow } from "./agentWorkspaceState";
import { SET_ON_THIS_AGENT } from "./agentWorkspaceState";
import "../styles/agent-workspace.css";

/**
 * What the table is, without saying what this agent came from. See the note above about
 * the caption.
 */
export const DIFF_CAPTION = "This agent beside the template it came from.";

/**
 * What an empty diff says.
 *
 * A copy of `NOTHING_TO_SHOW` in `src/components/DataTable.tsx`, spelled the same and
 * checked against it by test rather than imported: importing it would pull the table
 * library into this module's graph, and the split `src/App.tsx` measures exists because
 * that library is the largest thing in this console. The sentence is the same one for the
 * same reason the grid gives: empty because there is nothing and empty because nothing this
 * reader holds reaches anything are one event and must look like one.
 */
export const NOTHING_TO_SHOW = "Nothing to show.";

/** The two sides, in the order they are read. */
export const TEMPLATE_COLUMN = "Template";
export const INSTANCE_COLUMN = "This agent";
export const PATH_COLUMN = "Path";
export const SOURCE_COLUMN = "Set by";

/** How many columns a part's heading row spans. One number, so the two cannot disagree. */
const COLUMNS = 4;

/** One part of the composition and the paths that supply it. */
export interface PartGroup {
  readonly part: string;
  readonly rows: readonly DiffRow[];
}

/**
 * The rows grouped by the part each path supplies, in the order they arrived.
 *
 * Order is the caller's, which is `MANIFEST_PATHS` order when the rows came from
 * `brain.agents.upgrade._diff`, and that module explains why it walks the manifest rather
 * than the overlay: both lists then come back in one order whatever order an overlay was
 * written in, and a console renders the same review twice running. Re-sorting here would
 * throw that away and replace it with an order this file chose.
 */
export function groupByPart(rows: readonly DiffRow[]): PartGroup[] {
  const groups: { part: string; rows: DiffRow[] }[] = [];
  for (const row of rows) {
    const found = groups.find((group) => group.part === row.part);
    if (found) {
      found.rows.push(row);
    } else {
      groups.push({ part: row.part, rows: [row] });
    }
  }
  return groups;
}

/**
 * Whether this row is a value somebody set on this agent.
 *
 * One comparison, against the source the row carries. The two value columns are not read
 * here and must not be; see `DIVERGENCE_IS_READ_FROM_THE_OVERLAY_AND_NEVER_FROM_TWO_VALUES`.
 */
export function isSetOnThisAgent(row: DiffRow): boolean {
  return row.source === SET_ON_THIS_AGENT;
}

function DiffValue({ value }: { readonly value: string }) {
  return <span className="composition-diff__value">{value}</span>;
}

export function CompositionDiff({ rows }: { readonly rows: readonly DiffRow[] }) {
  const groups = groupByPart(rows);

  if (groups.length === 0) {
    return <p className="composition-diff__empty">{NOTHING_TO_SHOW}</p>;
  }

  return (
    <table className="composition-diff">
      <caption className="composition-diff__caption">{DIFF_CAPTION}</caption>
      <thead>
        <tr>
          <th scope="col">{PATH_COLUMN}</th>
          <th scope="col">{TEMPLATE_COLUMN}</th>
          <th scope="col">{INSTANCE_COLUMN}</th>
          <th scope="col">{SOURCE_COLUMN}</th>
        </tr>
      </thead>
      {groups.map((group) => (
        <tbody key={group.part}>
          <tr className="composition-diff__part">
            <th scope="rowgroup" colSpan={COLUMNS}>
              {group.part}
            </th>
          </tr>
          {group.rows.map((row) => (
            <tr
              key={row.path}
              className={
                isSetOnThisAgent(row)
                  ? "composition-diff__row composition-diff__row--local"
                  : "composition-diff__row"
              }
            >
              <th scope="row">
                <code>{row.path}</code>
              </th>
              <td>
                <DiffValue value={row.template} />
              </td>
              <td>
                <DiffValue value={row.instance} />
              </td>
              <td>
                <Chip label={row.source} />
                {row.setBy === undefined ? null : (
                  <>
                    {" "}
                    <code>{row.setBy}</code>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      ))}
    </table>
  );
}
