/**
 * The staff list screen's check: read the chosen list once, and show who setup would add.
 *
 * Drawn under the wizard's staff list questions by `pages/FirstRun.tsx`, and asked for only when
 * somebody presses a button, because reading a directory is a call to a server outside the install
 * and it names the company's people. `setup/staffList.ts` argues the pop-up and what a message from
 * it must carry; this draws it.
 *
 * **A spreadsheet is a file chosen here, and a directory is signed in to in a second window.** A
 * spreadsheet has nothing to sign in to, which is
 * `brain.identity.staff_source.A_SPREADSHEET_CANNOT_BE_AUTHENTICATED_AGAINST`. A directory needs an
 * application the company registered with it, and the words for what to register, and the return
 * address to register, are drawn from the server's own text before anything is asked for.
 *
 * **Nothing here is an answer to the wizard.** The client id, the client secret and the file stay
 * in this component's state, so none of them is in the review or in the appointment, and the secret
 * is sent once, in the read. A check is not required to finish setup either: the wizard's own
 * questions are what is written, and a company whose application is not registered yet can finish
 * and read its list from the console later.
 *
 * **What is drawn is a plan of who would be added, as a list and never a count**, which is
 * `pages/StaffSources.tsx`'s rule for the same `TrialView`, and a refusal is the server's sentence.
 * A 404 from any of the three routes is the wizard's one refusal sentence, for
 * `setup/wizard.ts`'s `A_SETUP_REFUSAL_NAMES_NO_REASON`.
 *
 * Task ids: M42.5.7
 */

import { useEffect, useRef, useState } from "react";
import { request } from "../api/client";
import { SETUP_REFUSED_MESSAGE } from "../setup/wizard";
import {
  REGISTRATION_PATH,
  SIGN_IN_PATH,
  SIGN_IN_WINDOW,
  SPREADSHEET,
  TRIAL_PATH,
  codeFrom,
  directoryTrialBody,
  newAttempt,
  returnAddress,
  sheetTrialBody,
  signInBody,
  type Registrations,
  type SignInAnswer,
  type TrialAsked,
} from "../setup/staffList";
import { readTrial, wasRead, type TrialAnswer, type TrialRun } from "../pages/staffSourcesQuery";
import { Notice } from "../ui/Notice";

export const CHECK_TITLE = "Check your staff list";
export const CHECK_LEDE =
  "Read the list once to see who it names. Nobody is added and nothing is stored at this step.";
export const CHOOSE_FIRST = "Choose where your staff list comes from, and it can be checked here.";
export const SHEET_LABEL = "Your staff list, saved as a CSV file";
export const READ_THE_SHEET = "Read the list";
export const SIGN_IN_AND_READ = "Sign in and read the list";
export const REGISTER_TITLE = "Before you sign in";
export const RETURN_ADDRESS_LABEL = "The return address to register";
export const CLIENT_ID_LABEL = "Client ID of the application you registered";
export const CLIENT_SECRET_LABEL = "Client secret of that application";
export const SECRET_IS_NOT_KEPT =
  "The secret is used for this one read and is not kept. Setup can finish without this check.";
export const READING = "Reading the list.";
export const WAITING_FOR_SIGN_IN = "Sign in in the window that opened. This page waits for it.";
export const POP_UP_BLOCKED =
  "The sign-in window did not open. Allow pop-ups for this address and press the button again.";
export const NOT_READ_TITLE = "That list could not be read";
export const WOULD_ADD_TITLE = "People setup would add";
export const NOBODY_TO_ADD = "The list names nobody who is still working there.";

interface Props {
  readonly setupCode: string;
  readonly source: string;
  readonly location: string;
}

type Shown =
  | { readonly kind: "run"; readonly run: TrialRun }
  | { readonly kind: "sentence"; readonly sentence: string }
  | null;

export function StaffListCheck({ setupCode, source, location }: Props) {
  const [registrations, setRegistrations] = useState<Registrations | null>(null);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [sheet, setSheet] = useState<File | null>(null);
  const [busy, setBusy] = useState("");
  const [shown, setShown] = useState<Shown>(null);
  const listening = useRef<((event: MessageEvent) => void) | null>(null);

  useEffect(() => {
    if (source === "" || source === SPREADSHEET || registrations !== null) {
      return;
    }
    void request<Registrations>(REGISTRATION_PATH, { atRoot: true }).then((result) => {
      if (result.ok) {
        setRegistrations(result.data);
      }
    });
  }, [source, registrations]);

  useEffect(
    () => () => {
      if (listening.current) {
        window.removeEventListener("message", listening.current);
      }
    },
    [],
  );

  // A different source is a different check, so what was shown for the last one goes.
  useEffect(() => {
    setShown(null);
    setBusy("");
  }, [source]);

  async function read(body: TrialAsked): Promise<void> {
    const result = await request<TrialAnswer>(TRIAL_PATH, { method: "POST", body, atRoot: true });
    setBusy("");
    if (!result.ok) {
      setShown({
        kind: "sentence",
        sentence: result.failure.status === 404 ? SETUP_REFUSED_MESSAGE : result.failure.message,
      });
      return;
    }
    const found = readTrial(result.data);
    setShown(wasRead(found) ? { kind: "run", run: found.panel } : { kind: "sentence", sentence: found.unread });
  }

  async function readSheet(): Promise<void> {
    if (sheet === null) {
      return;
    }
    setBusy(READING);
    setShown(null);
    await read(sheetTrialBody(setupCode, await sheet.text()));
  }

  async function signInAndRead(): Promise<void> {
    // Opened before anything is awaited, inside the press, which is what a pop-up blocker allows.
    const popup = window.open("about:blank", SIGN_IN_WINDOW, "popup,width=520,height=680");
    if (popup === null) {
      setShown({ kind: "sentence", sentence: POP_UP_BLOCKED });
      return;
    }
    setShown(null);
    setBusy(WAITING_FOR_SIGN_IN);
    const origin = window.location.origin;
    const attempt = await newAttempt();
    const started = await request<SignInAnswer>(SIGN_IN_PATH, {
      method: "POST",
      body: signInBody(setupCode, source, location, clientId, origin, attempt),
      atRoot: true,
    });
    if (!started.ok) {
      popup.close();
      setBusy("");
      const problem = (started.body as { problem?: unknown } | null)?.problem;
      setShown({
        kind: "sentence",
        sentence:
          started.failure.status === 404
            ? SETUP_REFUSED_MESSAGE
            : typeof problem === "string" && problem !== ""
              ? problem
              : started.failure.message,
      });
      return;
    }
    if (listening.current) {
      window.removeEventListener("message", listening.current);
    }
    const heard = (event: MessageEvent): void => {
      let code: string | null;
      try {
        code = codeFrom(event, origin, attempt);
      } catch (refused) {
        window.removeEventListener("message", heard);
        listening.current = null;
        setBusy("");
        setShown({ kind: "sentence", sentence: (refused as Error).message });
        return;
      }
      if (code === null) {
        return;
      }
      window.removeEventListener("message", heard);
      listening.current = null;
      setBusy(READING);
      void read(
        directoryTrialBody(setupCode, source, location, clientId, clientSecret, code, origin, attempt),
      );
    };
    listening.current = heard;
    window.addEventListener("message", heard);
    popup.location.href = started.data.address;
  }

  if (source === "") {
    return (
      <section className="first-run__section">
        <h2>{CHECK_TITLE}</h2>
        <p className="note">{CHOOSE_FIRST}</p>
      </section>
    );
  }

  const registration = registrations?.sources.find((one) => one.source === source);
  return (
    <section className="first-run__section">
      <h2>{CHECK_TITLE}</h2>
      <p>{CHECK_LEDE}</p>
      {source === SPREADSHEET ? (
        <div className="rjsf-field">
          <label className="control-label" htmlFor="first-run-staff-list-sheet">
            {SHEET_LABEL}
          </label>
          <input
            id="first-run-staff-list-sheet"
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => setSheet(event.target.files?.[0] ?? null)}
          />
          <div className="form-actions">
            <button
              type="button"
              className="button"
              disabled={sheet === null || busy !== ""}
              onClick={() => void readSheet()}
            >
              {READ_THE_SHEET}
            </button>
          </div>
        </div>
      ) : (
        <>
          {registration === undefined ? null : (
            <>
              <h3>{REGISTER_TITLE}</h3>
              <p>{registration.where}</p>
              <p>{registration.grant}</p>
              <dl className="fields">
                <div className="fields__row">
                  <dt>{RETURN_ADDRESS_LABEL}</dt>
                  <dd>
                    <code>{returnAddress(window.location.origin)}</code>
                  </dd>
                </div>
              </dl>
              <p className="note">{registration.location}</p>
            </>
          )}
          <div className="rjsf-field">
            <label className="control-label" htmlFor="first-run-staff-list-client-id">
              {CLIENT_ID_LABEL}
            </label>
            <input
              id="first-run-staff-list-client-id"
              type="text"
              className="form-control"
              value={clientId}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => setClientId(event.target.value)}
            />
          </div>
          <div className="rjsf-field">
            <label className="control-label" htmlFor="first-run-staff-list-client-secret">
              {CLIENT_SECRET_LABEL}
            </label>
            <input
              id="first-run-staff-list-client-secret"
              type="text"
              className="form-control"
              value={clientSecret}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => setClientSecret(event.target.value)}
            />
          </div>
          <p className="note">{SECRET_IS_NOT_KEPT}</p>
          <div className="form-actions">
            <button
              type="button"
              className="button"
              disabled={clientId.trim() === "" || clientSecret.trim() === "" || busy !== ""}
              onClick={() => void signInAndRead()}
            >
              {SIGN_IN_AND_READ}
            </button>
          </div>
        </>
      )}
      {busy === "" ? null : (
        <p className="note" role="status">
          {busy}
        </p>
      )}
      <Shown shown={shown} />
    </section>
  );
}

function Shown({ shown }: { readonly shown: Shown }) {
  if (shown === null) {
    return null;
  }
  if (shown.kind === "sentence") {
    return (
      <Notice title={NOT_READ_TITLE}>
        <p>{shown.sentence}</p>
      </Notice>
    );
  }
  const plan = shown.run.plan;
  if (plan === null || plan === undefined) {
    return (
      <Notice title={NOT_READ_TITLE}>
        <ul>
          {shown.run.refusals.map((why) => (
            <li key={why}>{why}</li>
          ))}
        </ul>
      </Notice>
    );
  }
  return (
    <>
      <h3>{WOULD_ADD_TITLE}</h3>
      {plan.would_add.length === 0 ? (
        <p className="note">{NOBODY_TO_ADD}</p>
      ) : (
        <ul className="roster" aria-label={WOULD_ADD_TITLE}>
          {plan.would_add.map((person) => (
            <li key={person.work_address}>
              {person.display_name} <code>{person.work_address}</code>
            </li>
          ))}
        </ul>
      )}
      {[...plan.refusals, ...plan.gaps, ...plan.withheld].map((sentence) => (
        <p key={sentence} className="note">
          {sentence}
        </p>
      ))}
    </>
  );
}
