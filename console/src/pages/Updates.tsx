/**
 * Version and updates: which release this install is on, and whether a newer one exists.
 *
 * M42.3.9 asks for this screen and gives the reason: nothing else reminds a client's IT team to
 * update. `brain.console.version_view` decides what it may say and `brain.install_routes` serves
 * it; this draws it.
 *
 * **The standing is the API's word and the two sentences under it are the API's sentences.**
 * `brain.console.version_view.ANSWERS` is total over nine answers, and every one of them is
 * written for somebody with a server and no source tree. A console that mapped the word to a
 * sentence of its own would be a second vocabulary for a closed set, out of step with the first
 * within a release, on the screen a client reads before deciding they are patched.
 *
 * **Nothing here is a tick and nothing here picks a colour.** Eight of the nine answers mean
 * some version of "this cannot be established or is not current", and the ninth is refused by
 * `Panel` unless a known running release, a telling, and a telling that has not gone off are all
 * behind it. Those are conditions this browser cannot check, so drawing reassurance here would
 * be the second place that decision is made. See
 * `A_TICK_DRAWN_HERE_IS_A_SECOND_OPINION_ABOUT_WHETHER_TO_WORRY`.
 *
 * **What is running is a release when there is one, and the commit is always beside it under
 * its own label.** The API sends the two as two fields, so this never picks a row out of the
 * facts by name to decide which one is the version. When no release is named the API's reason is
 * drawn where the release would be, as the main content rather than a caveat under a number,
 * because there is no number.
 *
 * **Nothing on this page waits for the release list.** The API answers from the last look that
 * finished and starts the next one beside the request, so the first load after a start can say
 * no look has finished yet. That is one of the nine answers and it is drawn like the others, with
 * the API's own instruction, rather than as a spinner a person waits in front of.
 *
 * **The link to a release's notes is drawn as the API sent it, and the API decided its scheme.**
 * `brain.console.version_view.Told` refuses notes that are not an https address, so a scheme
 * check here would be the second copy of a rule whose first copy is the one that runs on the
 * server. It opens without a referrer, so the release host is not told the console's address.
 *
 * Task ids: M27.7.25, M42.3.9
 */

import { useResource } from "../api/useResource";
import { Facts } from "../components/Facts";
import { Chip } from "../ui/Chip";
import { UPDATES_API_PATH, type Updates as UpdatesPanel } from "./installQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The one heading over any failure. The API's own sentence goes underneath it. */
export const SOMETHING_DID_NOT_WORK = "That did not work";

/**
 * What is said where the release would be, when the panel named no release.
 *
 * The heading only. The reason itself is the API's `cannot_say`, drawn below it unchanged: a
 * console that paraphrased it would be summarising the one paragraph on this screen that
 * explains why there is no version number to show.
 */
export const NO_RELEASE_NAMED = "This install does not name a release";

/** The words of the link to a release's notes. The address is the API's. */
export const READ_ITS_NOTES = "Read its release notes";

export function Updates() {
  const answer = useResource<UpdatesPanel>(UPDATES_API_PATH);
  const panel = answer.data;

  return (
    <article className="page">
      <h1>Version and updates</h1>
      <p className="lede">
        Which release is running here, and whether a newer one has been published. Nothing on this
        page asks anywhere outside this network unless this install was switched on to.
      </p>

      {answer.failure ? (
        <section className="card">
          <FailureNotice failure={answer.failure} />
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
            <dl className="fields" aria-label="The version running here">
              <div className="fields__row">
                <dt>release</dt>
                <dd>
                  {panel.running.tag ? (
                    <span>{panel.running.tag}</span>
                  ) : (
                    <>
                      <span>{NO_RELEASE_NAMED}</span>
                      <p className="note">{panel.running.cannot_say}</p>
                    </>
                  )}
                </dd>
              </div>
              {/*
               * The commit when the image reported one, and no row when it did not: the facts
               * below carry the sentence saying why it is unknown, and a second, empty row here
               * would be the placeholder `Facts` exists to refuse.
               */}
              {panel.running.commit ? (
                <div className="fields__row">
                  <dt>commit</dt>
                  <dd>
                    <span>{panel.running.commit}</span>
                  </dd>
                </div>
              ) : null}
            </dl>
            <Facts facts={panel.running.facts} label="Where a version could be read from" />
          </section>

          <section className="card">
            <h2>The newest published release</h2>
            {/*
             * Three shapes and each is drawn as itself. A telling carries which release, where its
             * notes are, who said so and when; a look that failed or a check that is off carries
             * the reason; no look finished yet carries neither, and what it gets is the API's
             * instruction, which already says that in words. No placeholder in any of the three.
             */}
            {panel.told ? (
              <dl className="fields" aria-label="The newest published release">
                <div className="fields__row">
                  <dt>newest release</dt>
                  <dd>{panel.told.tag}</dd>
                </div>
                {panel.told.notes ? (
                  <div className="fields__row">
                    <dt>notes</dt>
                    <dd>
                      <a href={panel.told.notes} rel="noreferrer">
                        {READ_ITS_NOTES}
                      </a>
                    </dd>
                  </div>
                ) : null}
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
