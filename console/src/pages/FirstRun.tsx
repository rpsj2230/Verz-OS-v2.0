/**
 * First run: sign in, give the setup code and the wizard's answers, approve the review, and land
 * on the console already signed in as the first administrator.
 *
 * **Sign-in comes first, and that order is forced by where the setup code is allowed to live.**
 * The code is held in this component's state and nowhere else: not a browser store, not a
 * cookie, not an address. The console's sign-in is authorisation code with PKCE, which is a
 * full page navigation to Keycloak and back, and a navigation ends this page's memory. So a
 * code typed before that navigation is a code lost by it, and the only ways to carry it across
 * are the ones this page refuses. Signing in before the code is typed means the whole wizard,
 * the appointment and the finishing screen happen inside one page lifetime, holding a token the
 * existing flow already refreshes. See `SIGN_IN_COMES_BEFORE_THE_CODE`.
 *
 * It is also the safer order on the server's own argument. `POST /setup/appointment` closes the
 * wizard for good, and `brain.setup_routes.NO_APPOINTMENT_WHERE_NOBODY_COULD_SIGN_IN_AFTER_IT`
 * is about exactly the install where the appointment lands and no sign-in can follow it. A
 * sign-in that fails here, because the realm has no account for this person or the redirect
 * address is not registered, fails before anything is written.
 *
 * Rejected: appointing first and then redirecting, carrying the code and the appointed principal
 * in the tab's session store or in the pending sign-in's `returnTo`. The first is the storage this page
 * exists to keep the code out of, and the second is a URL. Rejected also: asking for the code a
 * second time after the redirect. The principal id would still have to cross the navigation,
 * and a failed sign-in between the two requests leaves an administrator nobody can sign in as.
 * Rejected: a pop-up window for the sign-in. It is a second implementation of the flow in
 * `auth/session.ts`, and pop-up blockers make it fail for the person least able to diagnose it.
 *
 * **The form never submits itself.** Every `onSubmit` prevents the default, because a native
 * submission of a form with a code in it is a GET with the code in the query string, which is
 * then in history, in the server's access log and in any referrer. Inputs carry
 * `autoComplete="off"` so the browser does not keep the code in its own form history.
 *
 * **What a refusal is drawn as.** A 422 carries problems by step and field, and each is drawn
 * beside the input it names, in the catalogue's words. A 409 carries setting names and is drawn
 * as those names and nothing else, because the server compares against the running environment
 * and never sends a value. A 404 is one constant sentence whatever its body said: see
 * `A_SETUP_REFUSAL_NAMES_NO_REASON`.
 *
 * **Nothing sends a person here.** The root address does not detect an unfinished install and
 * redirect, because there is no route that says whether an install is finished, and there must
 * not be: that is the fact `EVERY_REFUSAL_BEFORE_THE_ANSWERS_IS_ONE_ANSWER` hides. The install
 * page tells the person holding the code which address to open.
 *
 * Task ids: M42.5.14
 */

import { useState, useSyncExternalStore } from "react";
import { useNavigate } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { clearSignInAttempts } from "../auth/pkce";
import { accessToken, beginSignIn, getSessionState, subscribe } from "../auth/session";
import {
  APPOINTMENT_PATH,
  FINISH_PATH,
  FINISH_TITLE,
  FIRST_RUN_PATH,
  REVIEW_TITLE,
  SCREENS,
  SETUP_REFUSED_MESSAGE,
  appointmentBody,
  finishBody,
  messageFor,
  placeProblems,
  stores,
  type AppointedView,
  type Answers,
  type Placed,
  type ProblemsView,
  type Question,
  type Screen,
  type SignInView,
  type StepKey,
} from "../setup/wizard";
import { Notice } from "../ui/Notice";

/** Why this page signs in before it asks for anything. */
export const SIGN_IN_COMES_BEFORE_THE_CODE =
  "The setup code lives in this page's memory only, and the sign-in is a full page navigation " +
  "that ends that memory. Signing in first puts the code, the appointment and the finishing " +
  "screen inside one page lifetime, and a sign-in that cannot work fails before anything is " +
  "written.";

/** The heading over the setting names a 409 carries. */
export const UNKEPT_TITLE = "Set these in your environment";

/** The heading over a refusal. The same for every refusal, so it says nothing either. */
export const NOT_CONTINUED_TITLE = "Setup did not continue";

/** Every screen the wizard counts, including the review and the finish, which ask nothing. */
const TOTAL_STEPS = SCREENS.length + 2;

const NO_PROBLEMS: Placed = Object.freeze({ byField: {}, byStep: {} });

type Told =
  | { readonly kind: "refused" }
  | { readonly kind: "unkept"; readonly names: readonly string[] }
  | { readonly kind: "failure"; readonly failure: ApiFailure }
  | { readonly kind: "session_ended" }
  | null;

/** The problems a 422 carries, or null when the body is not that document. */
function problemsIn(body: unknown): ProblemsView["problems"] | null {
  // A cast at the boundary, where proving the structure buys nothing: every entry is read back
  // through a `typeof` check before it is kept.
  const found = typeof body === "object" && body !== null ? (body as { problems?: unknown }).problems : undefined;
  if (!Array.isArray(found)) {
    return null;
  }
  return found.filter(
    (one): one is ProblemsView["problems"][number] =>
      typeof one === "object" &&
      one !== null &&
      typeof (one as Record<string, unknown>)["step"] === "string" &&
      typeof (one as Record<string, unknown>)["field"] === "string" &&
      typeof (one as Record<string, unknown>)["key"] === "string",
  );
}

/** The setting names a 409 carries, or null when the body is not that document. */
function unkeptIn(body: unknown): string[] | null {
  // The same boundary cast, narrowed the same way.
  const found = typeof body === "object" && body !== null ? (body as { unkept?: unknown }).unkept : undefined;
  if (!Array.isArray(found)) {
    return null;
  }
  return found.filter((one): one is string => typeof one === "string");
}

export function FirstRun() {
  const session = useSyncExternalStore(subscribe, getSessionState, getSessionState);

  if (session.status === "failed") {
    return (
      <div className="centred-panel">
        <Notice title="Could not sign you in">
          <p>{session.message}</p>
          <button
            type="button"
            className="button"
            onClick={() => {
              // A person retrying is not a redirect loop, as in `RequireSession`.
              clearSignInAttempts();
              void beginSignIn(FIRST_RUN_PATH);
            }}
          >
            Try again
          </button>
        </Notice>
      </div>
    );
  }

  if (session.status !== "authenticated") {
    return (
      <main className="first-run">
        <h1>Set up this system</h1>
        <p>
          Sign in first, with the account you will run this system as. You are asked for the
          setup code the installer printed after that, and nothing is written until you approve
          the review screen.
        </p>
        <button
          type="button"
          className="button"
          disabled={session.status === "authenticating"}
          onClick={() => void beginSignIn(FIRST_RUN_PATH)}
        >
          Sign in to begin
        </button>
      </main>
    );
  }

  // A separate component so that losing the session unmounts it, and the code and every
  // answer go with it rather than waiting for the next person at this browser.
  return <Wizard />;
}

function Wizard() {
  const navigate = useNavigate();
  const [at, setAt] = useState(0);
  const [code, setCode] = useState("");
  const [answers, setAnswers] = useState<Answers>({});
  const [skipped, setSkipped] = useState<ReadonlySet<StepKey>>(new Set());
  const [placed, setPlaced] = useState<Placed>(NO_PROBLEMS);
  const [told, setTold] = useState<Told>(null);
  const [busy, setBusy] = useState(false);
  const [appointed, setAppointed] = useState("");
  const [finishing, setFinishing] = useState(false);

  function valueOf(screen: Screen, question: Question): string {
    if (screen.key === "setup_code") {
      return code;
    }
    return answers[screen.key]?.[question.name] ?? "";
  }

  function setValue(screen: Screen, question: Question, value: string): void {
    if (screen.key === "setup_code") {
      setCode(value);
      return;
    }
    setAnswers((before) => ({
      ...before,
      [screen.key]: { ...(before[screen.key] ?? {}), [question.name]: value },
    }));
  }

  function carryOn(screen: Screen): void {
    if (screen.skippable && skipped.has(screen.key)) {
      const next = new Set(skipped);
      next.delete(screen.key);
      setSkipped(next);
    }
    setAt(at + 1);
  }

  function skipScreen(screen: Screen): void {
    setSkipped(new Set([...skipped, screen.key]));
    setAt(at + 1);
  }

  async function finish(principalId: string): Promise<void> {
    setBusy(true);
    setFinishing(true);
    setTold(null);
    const signed = await request<SignInView>(FINISH_PATH, {
      method: "POST",
      body: finishBody(code, principalId),
      atRoot: true,
    });
    if (!signed.ok) {
      setFinishing(false);
      setBusy(false);
      setTold(signed.failure.status === 404 ? { kind: "refused" } : { kind: "failure", failure: signed.failure });
      return;
    }
    setCode("");
    navigate("/", { replace: true });
  }

  async function submit(): Promise<void> {
    setBusy(true);
    setTold(null);
    // Checked before the appointment rather than discovered after it: the appointment closes
    // the wizard, and a finishing screen with no token to present cannot follow it.
    if (!(await accessToken())) {
      setBusy(false);
      setTold({ kind: "session_ended" });
      return;
    }
    const result = await request<AppointedView>(APPOINTMENT_PATH, {
      method: "POST",
      body: appointmentBody(code, answers, skipped),
      atRoot: true,
    });
    if (result.ok) {
      setPlaced(NO_PROBLEMS);
      setAppointed(result.data.principal_id);
      await finish(result.data.principal_id);
      return;
    }
    setBusy(false);
    const { status } = result.failure;
    const problems = status === 422 ? problemsIn(result.body) : null;
    const unkept = status === 409 ? unkeptIn(result.body) : null;
    if (status === 404) {
      setTold({ kind: "refused" });
    } else if (problems && problems.length > 0) {
      const next = placeProblems(problems);
      setPlaced(next);
      const first = SCREENS.findIndex(
        (screen) =>
          screen.key in next.byStep ||
          screen.questions.some((one) => `${screen.key}.${one.name}` in next.byField),
      );
      if (first >= 0) {
        setAt(first);
      }
    } else if (unkept && unkept.length > 0) {
      setTold({ kind: "unkept", names: unkept });
    } else {
      setTold({ kind: "failure", failure: result.failure });
    }
  }

  if (finishing) {
    return (
      <main className="first-run">
        <h1>{FINISH_TITLE}</h1>
        <p>Signing you in to the console.</p>
      </main>
    );
  }

  const screen = SCREENS[at];
  if (screen === undefined) {
    return (
      <main className="first-run">
        <p className="note">
          Step {SCREENS.length + 1} of {TOTAL_STEPS}
        </p>
        <h1>{REVIEW_TITLE}</h1>
        <p>
          Nothing has been written yet. Sending this appoints you as the first administrator
          and signs you in.
        </p>
        {SCREENS.filter(stores).map((one, index) => (
          <section key={one.key} className="first-run__section">
            <h2>{one.title}</h2>
            <StepProblems sentences={placed.byStep[one.key]} />
            {skipped.has(one.key) ? (
              <p>{messageFor("setup.review.skipped")}</p>
            ) : (
              <dl className="fields">
                {one.questions.map((question) => {
                  const given = valueOf(one, question).trim();
                  const shown = !given
                    ? messageFor("setup.review.not_given")
                    : question.secret
                      ? messageFor("setup.review.supplied")
                      : given;
                  return (
                    <div className="fields__row" key={question.name}>
                      <dt>{question.label}</dt>
                      <dd>{shown}</dd>
                    </div>
                  );
                })}
              </dl>
            )}
            <button
              type="button"
              className="button"
              disabled={busy || appointed !== ""}
              onClick={() => setAt(SCREENS.indexOf(one) >= 0 ? SCREENS.indexOf(one) : index)}
            >
              Change
            </button>
          </section>
        ))}
        <ToldNotice told={told} />
        <div className="form-actions">
          <button
            type="button"
            className="button"
            disabled={busy || appointed !== ""}
            onClick={() => setAt(at - 1)}
          >
            Back
          </button>
          {appointed ? (
            <button type="button" className="button" disabled={busy} onClick={() => void finish(appointed)}>
              Sign in again
            </button>
          ) : (
            <button type="button" className="button" disabled={busy} onClick={() => void submit()}>
              Set up this system
            </button>
          )}
        </div>
      </main>
    );
  }

  return (
    <main className="first-run">
      <p className="note">
        Step {at + 1} of {TOTAL_STEPS}
      </p>
      <h1>{screen.title}</h1>
      <StepProblems sentences={placed.byStep[screen.key]} />
      <form
        className="form"
        noValidate
        autoComplete="off"
        onSubmit={(event) => {
          // Never a native submission: see the module note.
          event.preventDefault();
          carryOn(screen);
        }}
      >
        {screen.questions.map((question) => (
          <Field
            key={question.name}
            screen={screen}
            question={question}
            value={valueOf(screen, question)}
            problems={placed.byField[`${screen.key}.${question.name}`] ?? []}
            onChange={(value) => setValue(screen, question, value)}
          />
        ))}
        <div className="form-actions">
          <button type="button" className="button" disabled={at === 0} onClick={() => setAt(at - 1)}>
            Back
          </button>
          {screen.skippable ? (
            <button type="button" className="button" onClick={() => skipScreen(screen)}>
              Skip this screen
            </button>
          ) : null}
          <button type="submit" className="button">
            Continue
          </button>
        </div>
      </form>
    </main>
  );
}

function StepProblems({ sentences }: { readonly sentences: readonly string[] | undefined }) {
  if (!sentences || sentences.length === 0) {
    return null;
  }
  return (
    <ul className="first-run__step-problems">
      {sentences.map((sentence, index) => (
        <li key={index}>{sentence}</li>
      ))}
    </ul>
  );
}

interface FieldProps {
  readonly screen: Screen;
  readonly question: Question;
  readonly value: string;
  readonly problems: readonly string[];
  readonly onChange: (value: string) => void;
}

function Field({ screen, question, value, problems, onChange }: FieldProps) {
  const id = `first-run-${screen.key}-${question.name}`;
  const problemId = `${id}-problem`;
  const invalid = problems.length > 0;
  const described = invalid ? { "aria-describedby": problemId } : {};
  return (
    <div className="rjsf-field">
      <label className="control-label" htmlFor={id}>
        {question.label}
        {question.required ? null : <span className="required">optional</span>}
      </label>
      {question.choices ? (
        <select
          id={id}
          className="form-control"
          value={value}
          aria-invalid={invalid}
          {...described}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Choose one</option>
          {question.choices.map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type="text"
          className="form-control"
          value={value}
          maxLength={question.maxChars}
          autoComplete="off"
          spellCheck={false}
          aria-invalid={invalid}
          {...described}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {invalid ? (
        <div id={problemId} className="first-run__problem">
          {problems.map((sentence, index) => (
            <p key={index}>{sentence}</p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ToldNotice({ told }: { readonly told: Told }) {
  if (told === null) {
    return null;
  }
  switch (told.kind) {
    case "refused":
      // No trace id and no body: see `A_SETUP_REFUSAL_NAMES_NO_REASON`.
      return (
        <Notice title={NOT_CONTINUED_TITLE}>
          <p>{SETUP_REFUSED_MESSAGE}</p>
        </Notice>
      );
    case "unkept":
      return (
        <Notice title={UNKEPT_TITLE}>
          <p>
            The running install does not carry these as you answered them, so nobody was
            appointed. Set each one in the install&rsquo;s environment file, restart the system,
            and send this screen again.
          </p>
          <ul className="first-run__names">
            {told.names.map((name) => (
              <li key={name}>
                <code>{name}</code>
              </li>
            ))}
          </ul>
        </Notice>
      );
    case "session_ended":
      return (
        <Notice title={NOT_CONTINUED_TITLE}>
          <p>
            Your sign-in ended before setup was sent, so nothing was written. Open this address
            again to sign in and start over.
          </p>
        </Notice>
      );
    case "failure":
      return (
        <Notice title={NOT_CONTINUED_TITLE} traceId={told.failure.traceId}>
          <p>{told.failure.message}</p>
        </Notice>
      );
  }
}
