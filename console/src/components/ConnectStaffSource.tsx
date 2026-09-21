/**
 * Connect a staff source: choose the kind, follow its steps, test it, save it, run its first sync.
 *
 * The owner asked for this on 2026-09-21: "give the option in the backend to connect their source
 * ... so I can just choose the source (Lark) and connect it", with the full steps shown. Every
 * sentence of the steps is the API's (`brain.console.staff_source_guide`), so this component draws
 * them and decides nothing about what a vendor needs.
 *
 * **Four presses, in the order they are safe.** A test reads a few pages and keeps nothing, so it
 * is not confirmed. Saving keeps the credential and points the nightly sync at the source, which
 * replaces whatever was there, so it is confirmed. The first sync is shown before it is applied,
 * at a separate address, and the apply is confirmed with what it will do. Saving is offered only
 * once a test of exactly the values in the boxes has read the directory, because the API reads
 * again before it keeps anything and a save that would be refused is a press that teaches nothing.
 *
 * **The secret is typed into a plain text field and never shown back.** A password field is
 * refused by `scripts/check-boundaries.mjs`, so each secret box is `autoComplete="off"` and
 * `spellCheck={false}`, as `ConnectSource.tsx` does. The values stay in this component's memory
 * until the first sync has been applied, because the application may write the vault and never
 * read it, so the dry run and the apply are sent the same values again; they are cleared then.
 *
 * **A reader who may not connect is shown the steps and no form.** `may_connect` is the API's
 * answer about the reader's own grants, and the API refuses every write again whatever this drew.
 *
 * Task ids: M27.7.2, M1.8.6
 */

import { useCallback, useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import {
  APPLY_FIRST_SYNC_API_PATH,
  blankLabels,
  blankValues,
  CONNECT_API_PATH,
  connectBody,
  CONNECTION_TEST_API_PATH,
  fillIn,
  heldBoxes,
  FIRST_SYNC_API_PATH,
  GUIDES_API_PATH,
  readConnectionTest,
  readFirstSync,
  readGuides,
  startingGuide,
  type ConnectionTest,
  type FirstSync,
  type Guide,
} from "../pages/staffSourcesQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { Notice } from "../ui/Notice";
import { ConfirmAction } from "./ConfirmAction";

export const CONNECT_HEADING = "Connect a staff source";
export const CONNECT_LEDE =
  "Choose where your company keeps its list of staff, follow the steps for it, then test the " +
  "connection. Nothing is saved until you save it, and nobody is added until you apply the first sync.";
export const CHOOSE_KIND = "1. Choose the kind of source";
export const FOLLOW_STEPS = "2. Follow these steps";
export const FILL_IN = "3. Fill in what the steps gave you";
export const FIRST_SYNC_HEADING = "4. Run the first sync";
export const AFTER_THAT = "After that";
export const SOURCE_KINDS_LABEL = "Kinds of staff source";
export const STEPS_LABEL = "Steps";
export const NOT_CONNECTABLE_HERE = "This source cannot be connected on this version";
export const STEPS_ONLY =
  "Connecting a source needs the install settings and credentials authorities over the whole " +
  "company. The steps are shown so you know what it will take.";

export const TEST_CONNECTION = "Test connection";
export const TESTING = "Reading a few pages of the directory.";
export const SAVE_AND_CONNECT = "Save and connect";
export const KEEP_AS_IT_IS = "Keep the current source";
export const SAVE_QUESTION_PREFIX = "Connect";
export const SAVE_CONSEQUENCE =
  "The credential is kept in the vault and replaces any kept before, and the nightly staff sync " +
  "reads this source from now on. The values are never shown again. Nobody is added until you " +
  "apply the first sync.";
export const TEST_FIRST = "Test the connection first. Save is offered once a test has read the directory.";
export const NOT_CONNECTED = "The source was not connected";

export const SHOW_FIRST_SYNC = "Show what the first sync would do";
export const APPLY_FIRST_SYNC = "Apply the first sync";
export const LEAVE_UNAPPLIED = "Not yet";
export const APPLY_QUESTION = "Apply the first sync now?";
export const APPLY_CONSEQUENCE =
  "The people listed above are added to the staff list, and anybody marked as having left is " +
  "marked. Nobody is given a sign-in, and a leaver's agents stop until a new owner takes them on. " +
  "The run is listed under What the nightly sync did.";
export const WOULD_ADD = "People the first sync would add";
export const WOULD_MARK_LEFT = "People it would mark as having left";
export const WOULD_RENAME = "People whose address it would move";
export const HELD_BACK = "What it would hold back";
export const REFUSED = "Why it would not apply";

/** A list of names, drawn only when there is one. Names, never a count of them. */
function Names({ label, names }: { readonly label: string; readonly names: readonly string[] }) {
  if (names.length === 0) {
    return null;
  }
  return (
    <>
      <h4>{label}</h4>
      <ul className="roster" aria-label={label}>
        {names.map((one) => (
          <li key={one}>{one}</li>
        ))}
      </ul>
    </>
  );
}

/** The plan a dry run returned. */
function Plan({ plan }: { readonly plan: FirstSync }) {
  return (
    <>
      <p>{plan.told}</p>
      <Names label={REFUSED} names={plan.refusals} />
      <Names label={WOULD_ADD} names={plan.added} />
      <Names label={WOULD_MARK_LEFT} names={plan.marked_left} />
      <Names label={WOULD_RENAME} names={plan.renamed} />
      <Names label={HELD_BACK} names={plan.withheld} />
    </>
  );
}

/** The form for one guide: its boxes, the test, the save, and the first sync after it. */
function ConnectForm({ guide, onConnected }: { readonly guide: Guide; readonly onConnected: () => void }) {
  const [values, setValues] = useState<Record<string, string>>(() => blankValues(guide));
  // Start on the credential the vault already holds when there is one, so it is not pasted twice.
  const [useHeld, setUseHeld] = useState((guide.held ?? "") !== "");
  const boxes = useHeld ? heldBoxes(guide) : guide.fields;
  const [blank, setBlank] = useState("");
  const [busy, setBusy] = useState(false);
  const [tested, setTested] = useState<ConnectionTest | null>(null);
  // The values the last successful test read with, so an edit after it asks for a new test.
  const [testedWith, setTestedWith] = useState("");
  const [savePending, setSavePending] = useState(false);
  const [connected, setConnected] = useState("");
  const [plan, setPlan] = useState<FirstSync | null>(null);
  const [applyPending, setApplyPending] = useState(false);
  const [applied, setApplied] = useState<FirstSync | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const snapshot = JSON.stringify(connectBody(guide, values));
  const readable = tested?.read === true && testedWith === snapshot;
  const prefix = `staff-source-${guide.source}`;

  /** Settles one answer: clears the busy flag, and keeps the failure or hands back the data. */
  const settle = useCallback((result: Awaited<ReturnType<typeof request<unknown>>>): unknown => {
    setBusy(false);
    if (!result.ok) {
      setFailure(result.failure);
      return null;
    }
    setFailure(null);
    return result.data;
  }, []);

  /** The two writes that keep nothing: the connection test and the first sync's dry run. */
  const look = useCallback(
    async (path: string): Promise<unknown> => {
      setBusy(true);
      return settle(await request<unknown>(path, { method: "POST", body: connectBody(guide, values) }));
    },
    [guide, values, settle],
  );

  function test(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setFailure(null);
    // Empty boxes are said beside the button, and nothing is sent. See `blankLabels`.
    const empty = blankLabels({ ...guide, fields: boxes }, values);
    setBlank(empty.length === 0 ? "" : fillIn(empty));
    if (empty.length > 0) {
      return;
    }
    if (useHeld) {
      // Nothing to test here: the application never reads a kept secret. Straight to the confirmation.
      setSavePending(true);
      return;
    }
    const sent = snapshot;
    void (async () => {
      const found = readConnectionTest(await look(CONNECTION_TEST_API_PATH));
      setTested(found);
      setTestedWith(found?.read === true ? sent : "");
    })();
  }

  // Saving and applying each have their own request, reached only from their confirmations.
  const save = useCallback(() => {
    setBusy(true);
    void (async () => {
      const data = settle(
        await request<unknown>(CONNECT_API_PATH, {
          method: "POST",
          body: connectBody(guide, values, useHeld),
        }),
      );
      setSavePending(false);
      if (data === null) {
        return;
      }
      const told = (data as { told?: unknown }).told;
      setConnected(typeof told === "string" ? told : SAVE_AND_CONNECT);
      onConnected();
    })();
  }, [guide, values, useHeld, settle, onConnected]);

  const showPlan = useCallback(() => {
    void (async () => {
      setPlan(readFirstSync(await look(FIRST_SYNC_API_PATH)));
    })();
  }, [look]);

  const apply = useCallback(() => {
    setBusy(true);
    void (async () => {
      const done = readFirstSync(
        settle(
          await request<unknown>(APPLY_FIRST_SYNC_API_PATH, {
            method: "POST",
            body: connectBody(guide, values),
          }),
        ),
      );
      setApplyPending(false);
      setApplied(done);
      if (done !== null) {
        // The first sync is done; nothing needs the typed values any longer.
        setValues(blankValues(guide));
        onConnected();
      }
    })();
  }, [guide, values, settle, onConnected]);

  return (
    <div className="form" role="group" aria-label={`${CONNECT_HEADING}: ${guide.title}`}>
      <h3>{FILL_IN}</h3>
      {failure === null ? null : <FailureNotice failure={failure} title={NOT_CONNECTED} />}
      {(guide.held ?? "") === "" || connected !== "" ? null : (
        <label className="control-label">
          <input
            type="checkbox"
            name="use_held"
            checked={useHeld}
            disabled={busy}
            onChange={(event) => {
              setUseHeld(event.target.checked);
            }}
          />{" "}
          {guide.held}
        </label>
      )}
      <form className="form" noValidate autoComplete="off" onSubmit={test}>
        {boxes.map((box) => (
          <div className="rjsf-field" key={box.key}>
            <label className="control-label" htmlFor={`${prefix}-${box.key}`}>
              {box.label}
            </label>
            <input
              id={`${prefix}-${box.key}`}
              className="form-control"
              type="text"
              name={box.key}
              value={values[box.key] ?? ""}
              placeholder={box.secret ? "" : box.example}
              autoComplete="off"
              spellCheck={false}
              disabled={busy || connected !== ""}
              onChange={(event) => {
                setValues({ ...values, [box.key]: event.target.value });
              }}
            />
            <p className="field-description">{box.help}</p>
          </div>
        ))}
        {blank === "" ? null : <p className="field-problem">{blank}</p>}
        {connected !== "" ? null : (
          <div className="form-actions">
            <button type="submit" className="button" disabled={busy}>
              {useHeld ? SAVE_AND_CONNECT : TEST_CONNECTION}
            </button>
            {useHeld ? null : (
            <button
              type="button"
              className="button"
              disabled={busy || !readable}
              onClick={() => {
                setSavePending(true);
              }}
            >
              {SAVE_AND_CONNECT}
            </button>
            )}
          </div>
        )}
      </form>
      {busy ? (
        <p className="note" role="status">
          {TESTING}
        </p>
      ) : null}
      {tested === null ? null : <p className={tested.read ? "note" : "field-problem"}>{tested.told}</p>}
      {connected !== "" || readable || tested === null ? null : <p className="note">{TEST_FIRST}</p>}
      {!savePending ? null : (
        <ConfirmAction
          question={`${SAVE_QUESTION_PREFIX} ${guide.title}?`}
          consequence={SAVE_CONSEQUENCE}
          confirmLabel={SAVE_AND_CONNECT}
          cancelLabel={KEEP_AS_IT_IS}
          busy={busy}
          onConfirm={save}
          onCancel={() => {
            setSavePending(false);
          }}
        />
      )}
      {connected === "" || !useHeld ? null : <p className="note">{connected}</p>}
      {connected === "" || useHeld ? null : (
        <>
          <p className="note">{connected}</p>
          <h3>{FIRST_SYNC_HEADING}</h3>
          {applied !== null ? (
            <p className="note">{applied.told}</p>
          ) : (
            <>
              <div className="form-actions">
                <button type="button" className="button" disabled={busy} onClick={showPlan}>
                  {SHOW_FIRST_SYNC}
                </button>
                <button
                  type="button"
                  className="button"
                  disabled={busy || plan === null || !plan.safe_to_apply}
                  onClick={() => {
                    setApplyPending(true);
                  }}
                >
                  {APPLY_FIRST_SYNC}
                </button>
              </div>
              {plan === null ? null : <Plan plan={plan} />}
            </>
          )}
          {!applyPending ? null : (
            <ConfirmAction
              question={APPLY_QUESTION}
              consequence={APPLY_CONSEQUENCE}
              confirmLabel={APPLY_FIRST_SYNC}
              cancelLabel={LEAVE_UNAPPLIED}
              busy={busy}
              onConfirm={apply}
              onCancel={() => {
                setApplyPending(false);
              }}
            />
          )}
        </>
      )}
    </div>
  );
}

/** The whole section. Drawn only once the guides have been read; nothing at all otherwise. */
export function ConnectStaffSource({ onConnected }: { readonly onConnected: () => void }) {
  const answer = useResource<unknown>(GUIDES_API_PATH);
  const guides = readGuides(answer.data);
  const [picked, setPicked] = useState<string | null>(null);
  if (guides === null || guides.guides.length === 0) {
    return null;
  }
  const guide = guides.guides.find((one) => one.source === picked) ?? startingGuide(guides.guides);
  if (guide === null) {
    return null;
  }
  return (
    <section className="card" aria-label={CONNECT_HEADING}>
      <h2>{CONNECT_HEADING}</h2>
      <p>{CONNECT_LEDE}</p>
      <h3>{CHOOSE_KIND}</h3>
      <ul className="roster" aria-label={SOURCE_KINDS_LABEL}>
        {guides.guides.map((one) => (
          <li key={one.source}>
            <button
              type="button"
              className="button"
              aria-pressed={one.source === guide.source}
              onClick={() => {
                setPicked(one.source);
              }}
            >
              {one.title}
            </button>
          </li>
        ))}
      </ul>
      <h3>{FOLLOW_STEPS}</h3>
      <p className="note">{guide.where}</p>
      <ol aria-label={`${STEPS_LABEL}: ${guide.title}`}>
        {guide.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      {guide.connectable ? null : (
        <Notice title={NOT_CONNECTABLE_HERE}>
          <p>{guide.unavailable}</p>
        </Notice>
      )}
      {!guides.may_connect ? (
        <p className="note">{STEPS_ONLY}</p>
      ) : guide.connectable ? (
        <ConnectForm key={guide.source} guide={guide} onConnected={onConnected} />
      ) : null}
      <h3>{AFTER_THAT}</h3>
      <p>{guides.schedule}</p>
    </section>
  );
}
