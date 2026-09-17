/**
 * First run's data sources step, finished: the sources named on the Data sources screen, offered
 * for connecting once the first administrator is signed in, through the Connectors screen's own
 * form and request. Skippable, and every word of it says the same can be done later from
 * Connectors.
 *
 * **After the appointment, and never inside it.** Connecting a source writes a key into the vault
 * and records who did, under `admin:connector`. Before the appointment nobody holds that grant and
 * the only authority on the page is the setup code, which exists to appoint one administrator and
 * nothing wider; carrying a key in the appointment would make the setup code a way to write a
 * source's key, attributed to no person. After the finishing screen has bound the sign-in, the page
 * holds the administrator's own token, so the request is exactly the one the console makes, judged
 * by the same route, confirmed in the same words and recorded against the person. See
 * `CONNECTING_WAITS_FOR_THE_ADMINISTRATOR`.
 *
 * **The Data sources screen is what decides whether this step is shown.** It is skippable and
 * commits nothing, which `brain.setup_wizard.A_CONNECTION_SKIPPED_NOW_IS_NOT_A_CONNECTION_REFUSED`
 * argues; a person who skipped it lands on the console as before, and a person who named sources
 * is offered each one here. A name the console can connect gets the form, a name this release
 * connects only at the server gets the API's reason, and a name it has no connector for says so.
 *
 * **A failure here does not undo first run.** The administrator is appointed and signed in before
 * this step draws, so a vault that refuses, or a read the API will not answer, is drawn as the
 * API's sentence with the way on to the console beside it.
 *
 * Task ids: M42.5.9
 */

import { useState } from "react";
import { useResource } from "../api/useResource";
import { ConnectSource } from "../components/ConnectSource";
import {
  CONNECTORS_API_PATH,
  type Connectable,
  type Connectors,
} from "../pages/connectorsQuery";
import { FailureNotice } from "../ui/FailureNotice";
import type { Answers, StepKey } from "./wizard";

/** Why the step comes after the appointment rather than inside it. */
export const CONNECTING_WAITS_FOR_THE_ADMINISTRATOR =
  "Connecting a source writes its key into the vault under the connector grant, and before the " +
  "appointment nobody holds that grant: the setup code appoints one administrator and must not " +
  "become a way to write a key attributed to nobody. So the sources named during setup are " +
  "connected once the administrator is signed in, through the console's own request.";

export const CONNECT_SOURCES_TITLE = "Connect your data sources";

/** Said above the sources, whatever happens below. */
export const CONNECT_LATER =
  "You named these on the Data sources screen. Connect each one now, or skip this: any source " +
  "can be connected at any time from Connectors in the console, in exactly the same way.";

export const SKIP_CONNECTING = "Skip, and connect sources later from Connectors";
export const ON_TO_THE_CONSOLE = "Open the console";

/** Said for a name this release has no connector for. */
export const NO_SUCH_SOURCE =
  "This system has no connector by that name. Connectors in the console lists every source it " +
  "can connect.";

/** Said for a source the signed-in person may not connect. Their own grant, nobody else's. */
export const NOT_YOURS =
  "Connecting this source needs the connector installation grant over it, which you do not hold.";

/** The heading over a read of the sources that did not work. */
export const SOURCES_NOT_READ = "The sources this system can connect could not be read";

/** The sources named on the Data sources screen, or none when it was skipped or left blank. */
export function namedSources(answers: Answers, skipped: ReadonlySet<StepKey>): readonly string[] {
  if (skipped.has("connections")) {
    return [];
  }
  const typed = answers.connections?.["connections"] ?? "";
  const names = typed
    .split(",")
    .map((one) => one.trim())
    .filter((one) => one !== "");
  return [...new Set(names)];
}

function SourceSection({
  name,
  page,
  onConnected,
}: {
  readonly name: string;
  readonly page: Connectors;
  readonly onConnected: (told: string) => void;
}) {
  const source: Connectable | undefined = page.connectable.find((one) => one.name === name);
  const elsewhere = page.not_connectable.find((one) => one.name === name);
  return (
    <section className="first-run__section" aria-label={source?.label ?? elsewhere?.label ?? name}>
      <h2>{source?.label ?? elsewhere?.label ?? name}</h2>
      {source !== undefined ? (
        source.may_connect ? (
          <ConnectSource
            source={source}
            confirmation={page.confirm_connect}
            keyMaxChars={page.key_max_chars}
            keyBlank={page.key_blank}
            onConnected={onConnected}
          />
        ) : (
          <p>{NOT_YOURS}</p>
        )
      ) : elsewhere !== undefined ? (
        <p>{elsewhere.why}</p>
      ) : (
        <p>{NO_SUCH_SOURCE}</p>
      )}
    </section>
  );
}

export function ConnectSourcesStep({
  named,
  kept,
  onDone,
}: {
  readonly named: readonly string[];
  /** What first run says about the provider key, when it kept one. */
  readonly kept: string | null;
  readonly onDone: () => void;
}) {
  const answer = useResource<Connectors>(CONNECTORS_API_PATH);
  const [connected, setConnected] = useState<Record<string, string>>({});
  const page = answer.data;

  return (
    <main className="first-run">
      <h1>{CONNECT_SOURCES_TITLE}</h1>
      {kept === null ? null : <p>{kept}</p>}
      <p>{CONNECT_LATER}</p>
      {answer.failure ? <FailureNotice failure={answer.failure} title={SOURCES_NOT_READ} /> : null}
      {answer.busy ? (
        <p className="note" role="status">
          Reading which sources this system can connect.
        </p>
      ) : null}
      {page === null ? null : (
        <>
          <p>{page.connecting}</p>
          {page.vault_told === "" ? null : <p className="note">{page.vault_told}</p>}
          {named.map((name) =>
            name in connected ? (
              <section className="first-run__section" key={name} aria-label={name}>
                <h2>{name}</h2>
                <p>{connected[name]}</p>
              </section>
            ) : (
              <SourceSection
                key={name}
                name={name}
                page={page}
                onConnected={(told) => {
                  setConnected((before) => ({ ...before, [name]: told }));
                }}
              />
            ),
          )}
        </>
      )}
      <div className="form-actions">
        <button type="button" className="button" onClick={onDone}>
          {Object.keys(connected).length === 0 ? SKIP_CONNECTING : ON_TO_THE_CONSOLE}
        </button>
      </div>
    </main>
  );
}
