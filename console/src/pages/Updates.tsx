/**
 * Version and updates: which release this install is on, and whether anything newer exists.
 *
 * M42.3.9 asks for this screen and gives the reason: nothing else reminds a client's IT team to
 * update. `brain.console.version_view` decided what it may say on 2026-09-10 and nothing could
 * open it until now, which made the leaf a panel a client could not read.
 *
 * **The standing is the API's word and the two sentences under it are the API's sentences.**
 * `brain.console.version_view.ANSWERS` is total over eight answers, and every one of them is
 * written for somebody with a server and no source tree. A console that mapped the word to a
 * sentence of its own would be a second vocabulary for a closed set, out of step with the first
 * within a release, on the screen a client reads before deciding they are patched.
 *
 * **Nothing here is a tick and nothing here picks a colour.** Seven of the eight answers mean
 * some version of "this cannot be established", and the eighth is refused by `Panel` unless a
 * known running release, a telling, and a telling that has not gone off are all behind it.
 * Those are conditions this browser cannot check, so drawing reassurance here would be the
 * second place that decision is made. See
 * `A_TICK_DRAWN_HERE_IS_A_SECOND_OPINION_ABOUT_WHETHER_TO_WORRY`.
 *
 * **The three version statements are shown even when they disagree, and especially then.** The
 * common answer on an install that has never run the update script is that the release marker
 * and the running containers say different things and neither is wrong, so the panel names no
 * release at all and says which two statements it read. That sentence is the page's main
 * content in that state, not a caveat under a number, because there is no number.
 *
 * **What was said, and how long ago, are two facts and both are drawn.** A telling is only
 * worth what its source is worth, so `by` is shown beside the tag rather than left out for
 * tidiness: an administrator who read the release notes this morning and a value typed once
 * during setup render identically without it.
 *
 * Task ids: M27.7.25
 */

import { useResource } from "../api/useResource";
import { Facts } from "../components/Facts";
import { Chip } from "../ui/Chip";
import { Notice } from "../ui/Notice";
import { UPDATES_API_PATH, type Updates as UpdatesPanel } from "./installQuery";

/** The one heading over any failure. The API's own sentence goes underneath it. */
export const SOMETHING_DID_NOT_WORK = "That did not work";

/**
 * What is said above the three statements when the panel named no release.
 *
 * The heading only. The reason itself is the API's `cannot_say`, drawn below it unchanged: a
 * console that paraphrased it would be summarising the one paragraph on this screen that
 * explains why there is no version number to show.
 */
export const NO_RELEASE_NAMED = "This install does not name a release";

export function Updates() {
  const answer = useResource<UpdatesPanel>(UPDATES_API_PATH);
  const panel = answer.data;

  return (
    <article className="page">
      <h1>Version and updates</h1>
      <p className="lede">
        Which release is running here, and whether anything newer has been recorded. Nothing on
        this page asks anywhere outside this network unless this install was set to.
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

      {panel ? (
        <>
          <section className="card">
            <h2>Where this install stands</h2>
            <p>
              <Chip label={panel.standing} />
            </p>
            <p>{panel.says}</p>
            <p className="note">{panel.what_to_do}</p>
          </section>

          <section className="card">
            <h2>What is running</h2>
            {panel.running.tag ? (
              <p>
                <Chip label={panel.running.tag} />
              </p>
            ) : (
              <>
                <p>{NO_RELEASE_NAMED}</p>
                <p className="note">{panel.running.cannot_say}</p>
              </>
            )}
            <Facts facts={panel.running.facts} label="Where a version could be read from" />
          </section>

          <section className="card">
            <h2>What this install was told</h2>
            {/*
             * Three shapes and each is drawn as itself. A telling carries who said so and when;
             * an install that asked and got nothing carries the reason; an install that has
             * never been told anything carries neither, and what it gets is the standing above,
             * which already says that in words. No placeholder in any of the three.
             */}
            {panel.told ? (
              <dl className="fields" aria-label="What this install was told">
                <div className="fields__row">
                  <dt>newest release</dt>
                  <dd>{panel.told.tag}</dd>
                </div>
                <div className="fields__row">
                  <dt>said by</dt>
                  <dd>{panel.told.by}</dd>
                </div>
                <div className="fields__row">
                  <dt>said at</dt>
                  <dd>{panel.told.at}</dd>
                </div>
              </dl>
            ) : null}

            {panel.unanswered ? (
              <>
                <p>
                  <Chip label={panel.unanswered.why} />
                </p>
                <p className="note">{panel.unanswered.detail}</p>
              </>
            ) : null}

            {!panel.told && !panel.unanswered ? (
              <p className="note">{panel.what_to_do}</p>
            ) : null}
          </section>
        </>
      ) : null}
    </article>
  );
}
