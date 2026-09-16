/**
 * This install: what is actually running, each fact labelled with how firmly it is known.
 *
 * The first question of every support conversation, and until this page it was answerable only
 * by somebody with the server's shell. `brain.console.installation.install_facts` decided what
 * may be shown here on 2026-09-08 and nothing could open it: `brain.ops.console_screens` counts
 * that as a screen nobody has and named the module on every run of the traceability sweep.
 *
 * **This page adds no interpretation to any value**, which is `Overview.tsx`'s rule applied to
 * a harder case. The release is `unknown` outside a built image, the migration level is
 * `declared` because the route does not open a connection to measure it, and both arrive with a
 * sentence saying so. A page that summarised those into "healthy" would be composing a verdict
 * out of values whose whole point is that they are three different kinds of statement.
 *
 * **There is no refresh control and no timestamp on the page.** The facts are read when the
 * page is opened and they do not move: a release does not change without a deploy and a profile
 * does not change without an operator. A relative age drawn beside them would be the one moving
 * number on a screen full of still ones, and it would be measured from when this browser asked
 * rather than from when anything happened.
 *
 * A failure is the API's own sentence and the trace id. Including a 404, which here means the
 * caller may not read this screen, and saying so would be the console explaining a refusal it
 * did not observe and cannot distinguish from an absence.
 *
 * Task ids: M27.7.25
 */

import { useResource } from "../api/useResource";
import { Facts } from "../components/Facts";
import { Notice } from "../ui/Notice";
import { factsOf, INSTALL_API_PATH, type InstallFacts } from "./installQuery";

/** The one heading over any failure. The API's own sentence goes underneath it. */
export const SOMETHING_DID_NOT_WORK = "That did not work";

export function Install() {
  const answer = useResource<InstallFacts>(INSTALL_API_PATH);
  const facts = factsOf(answer.data);

  return (
    <article className="page">
      <h1>This install</h1>
      <p className="lede">
        What is actually running here, with where each statement came from beside it.
      </p>

      <section className="card">
        <h2>What is running</h2>

        {answer.failure ? (
          <Notice title={SOMETHING_DID_NOT_WORK} traceId={answer.failure.traceId}>
            <p>{answer.failure.message}</p>
          </Notice>
        ) : null}

        {answer.busy ? (
          <p className="note" role="status">
            Loading.
          </p>
        ) : null}

        {facts.length > 0 ? <Facts facts={facts} label="What is running" /> : null}
      </section>
    </article>
  );
}
