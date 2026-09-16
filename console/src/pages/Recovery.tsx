/**
 * Backup and recovery: what has been copied, what has been read back, and one verdict from both.
 *
 * `docs/needs-rupash.md` item 44 says this is the screen somebody checks before deciding not to
 * worry, and `brain.console.recovery_view` is built entirely around the state that reads best
 * and is worst: a copy taken three hours ago, every indicator green, and nobody has ever read
 * one back. This page draws that module's answer and adds nothing to it.
 *
 * **There is no tick anywhere on this page and no indicator that could be one.** The verdict is
 * a word from a closed set of eight with two sentences under it, both the API's. Seven of the
 * eight mean some version of "this cannot be established", and the eighth is refused by `Panel`
 * without copies, without a verification, with a newer failed attempt, with a drill overdue,
 * with a coverage outside the recovery point, or with any record that could not be read. Those
 * are conditions this browser cannot check.
 *
 * **Every coverage gets a row, including the ones nothing copies.** `copy_states` returns one
 * per coverage for that reason: a coverage left out is an absence a reader would have to notice
 * by counting, and a screen showing two rows where a healthy install shows three has reported
 * the missing one by subtraction. So the page draws what it was sent and never filters.
 *
 * **Last verified restore is a fact and not a date.** It arrives as a
 * `brain.console.installation.Fact` and is drawn through `Facts`, which has no placeholder: an
 * install where no restore has ever verified renders the sentence saying what would have to
 * happen, rather than a dash beside a fresh backup timestamp.
 *
 * **Records that could not be read are named at the top rather than counted.** The run that
 * falls over is the run whose record is truncated, so the missing one is the one most likely to
 * matter, and a reader who is told how many were unreadable cannot go and look at any of them.
 *
 * **There is no drill control here, and its absence is the leaf's answer rather than an
 * oversight.** M30.3.9 asks for a one-click drill. A drill is a write, no console module
 * performs one, and `brain.console.recovery_view` declines that leaf in those words; a button
 * here would be this console deciding it from the side that renders.
 *
 * M27.7.26 is this screen and is deliberately not claimed, here or in the commit that adds
 * it. The leaf asks for the backup, the last verified restore and the drill, and on every
 * install today the page shows none of the three: nothing on the process that answers it
 * can read the backup bucket, and the drill is a write no console module performs. A
 * screen that is reachable and cannot answer is not the leaf.
 *
 * Task ids: none
 */

import { useResource } from "../api/useResource";
import { Facts } from "../components/Facts";
import { Chip } from "../ui/Chip";
import { Notice } from "../ui/Notice";
import { RECOVERY_API_PATH, readRecovery, wasRead, type Recovery as RecoveryBody } from "./installQuery";

/** The one heading over any failure. The API's own sentence goes underneath it. */
export const SOMETHING_DID_NOT_WORK = "That did not work";

/** The heading over the state where this install could not look at its own copies. */
export const NOTHING_LOOKED = "Nothing here has looked at your copies";

/** The heading over the records in the bucket that could not be read. */
export const RECORDS_THAT_COULD_NOT_BE_READ = "Records that could not be read";

export function Recovery() {
  const answer = useResource<RecoveryBody>(RECOVERY_API_PATH);
  const read = readRecovery(answer.data);

  return (
    <article className="page">
      <h1>Backup and recovery</h1>
      <p className="lede">
        What has been copied, when a restore was last verified, and whether a rehearsal is owed.
      </p>

      {answer.failure ? (
        <section className="card">
          <Notice title={SOMETHING_DID_NOT_WORK} traceId={answer.failure.traceId}>
            <p>{answer.failure.message}</p>
          </Notice>
        </section>
      ) : null}

      {answer.busy ? (
        <p className="note" role="status">
          Loading.
        </p>
      ) : null}

      {/*
       * The unread state is a notice rather than an empty panel, and it is the whole page when
       * it happens. An empty panel here would render as an install whose backups have never
       * run, which is an alarming word for a fact nobody established, and it would be believed.
       */}
      {!answer.busy && !answer.failure && !wasRead(read) ? (
        <section className="card">
          <Notice title={NOTHING_LOOKED}>
            <p>{read.unread}</p>
          </Notice>
        </section>
      ) : null}

      {wasRead(read) ? (
        <>
          {read.panel.unreadable.length > 0 ? (
            <section className="card">
              <Notice title={RECORDS_THAT_COULD_NOT_BE_READ}>
                <ul>
                  {read.panel.unreadable.map((one) => (
                    <li key={one.where}>
                      <code>{one.where}</code> {one.why}
                    </li>
                  ))}
                </ul>
              </Notice>
            </section>
          ) : null}

          <section className="card">
            <h2>Where this install stands</h2>
            <p>
              <Chip label={read.panel.assurance} />
            </p>
            <p>{read.panel.says}</p>
            <p className="note">{read.panel.what_to_do}</p>
            <Facts facts={[read.panel.last_verified]} label="Last verified restore" />
            {/*
             * Two more values the panel carries, drawn as the API's own `true`, `false` or
             * number rather than as an indicator. That is `matrixQuery.ts`'s rule about
             * `enabled` on a rung: a boolean the console turned into a symbol is a boolean the
             * console decided the meaning of, and on this screen the meaning is the verdict
             * above, which was computed where the conditions are.
             *
             * `measured_rto_seconds` is null when no restore has ever verified, and the row is
             * then absent rather than present and empty, which is `Overview.tsx`'s rule: a row
             * rendered with nothing in it is a shape where a fact would be.
             */}
            <dl className="fields" aria-label="The rehearsal">
              <div className="fields__row">
                <dt>a rehearsal is owed</dt>
                <dd>{String(read.panel.drill_is_due)}</dd>
              </div>
              {read.panel.measured_rto_seconds === null ||
              read.panel.measured_rto_seconds === undefined ? null : (
                <div className="fields__row">
                  <dt>the last verified restore took</dt>
                  <dd>{`${String(read.panel.measured_rto_seconds)}s`}</dd>
                </div>
              )}
            </dl>
          </section>

          {read.panel.copies.map((copy) => (
            <section className="card" key={copy.coverage}>
              <h2>{copy.coverage}</h2>
              <Facts facts={copy.facts} label={`Copies of ${copy.coverage}`} />
              <dl className="fields" aria-label={`${copy.coverage} against the promise`}>
                <div className="fields__row">
                  <dt>inside the recovery point</dt>
                  <dd>{String(copy.within_objective)}</dd>
                </div>
                <div className="fields__row">
                  <dt>the recovery point this profile promises</dt>
                  <dd>{`${String(copy.objective_seconds)}s`}</dd>
                </div>
              </dl>
            </section>
          ))}
        </>
      ) : null}
    </article>
  );
}
