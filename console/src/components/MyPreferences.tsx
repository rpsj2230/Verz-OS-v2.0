/**
 * A person's own settings, in My workspace: whether personal learning is on, which channel they are
 * reached on first, what each channel may tell them, where an approval waits, and when digests are
 * held.
 *
 * Every control is the API's own: the card offers the channels the person is connected on and the
 * places an approval may wait, sends the whole of where they are reached in one request, and shows
 * a refusal in the API's words. Switching learning off says what it costs and removes nothing.
 * Quiet hours say they never hold an approval.
 *
 * Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4, M27.16.2
 */

import { useCallback, useEffect, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import {
  LEARNING_API_PATH,
  PREFERENCES_API_PATH,
  QUIET_API_PATH,
  REACH_API_PATH,
  draftOf,
  learningBody,
  reachBody,
  ticked,
  toggled,
  type Preferences,
  type ReachDraft,
} from "../pages/myPreferencesQuery";
import { FailureNotice } from "../ui/FailureNotice";

export const PREFERENCES_CAPTION = "How I am reached";
export const LEARNING_OFF_LABEL = "Stop learning from me";
export const LEARNING_ON_LABEL = "Learn from me again";
export const SAVE_REACH_LABEL = "Save where I am reached";
export const SAVE_QUIET_LABEL = "Save quiet hours";
export const CLEAR_QUIET_LABEL = "Clear quiet hours";
export const NO_CHANNELS = "You are not connected on any chat channel.";
export const NOT_SET = "No preference";

function Reading() {
  return (
    <p className="note" role="status">
      Reading your settings.
    </p>
  );
}

export function MyPreferences() {
  const [version, setVersion] = useState(0);
  const answer = useResource<Preferences>(PREFERENCES_API_PATH, version);
  const [draft, setDraft] = useState<ReachDraft | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  useEffect(() => {
    if (answer.data !== null) {
      setDraft(draftOf(answer.data));
      setStart(answer.data.quiet?.start ?? "");
      setEnd(answer.data.quiet?.end ?? "");
    }
  }, [answer.data]);

  const send = useCallback((call: () => Promise<Awaited<ReturnType<typeof request<Preferences>>>>) => {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await call();
      setBusy(false);
      if (result.ok) {
        setVersion((current) => current + 1);
        return;
      }
      setFailure(result.failure);
    })();
  }, []);

  const saved = answer.data;
  return (
    <section className="card">
      <h2>{PREFERENCES_CAPTION}</h2>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {answer.failure ? (
        <FailureNotice failure={answer.failure} />
      ) : saved === null || draft === null ? (
        <Reading />
      ) : (
        <>
          <div>
            <h3>Learning</h3>
            <p>{saved.learning.opted_out ? "Learning from you is off." : "Learning from you is on."}</p>
            <p className="note">{saved.learning.cost}</p>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => {
                send(() =>
                  request<Preferences>(LEARNING_API_PATH, {
                    method: "POST",
                    body: learningBody(!saved.learning.opted_out),
                  }),
                );
              }}
            >
              {saved.learning.opted_out ? LEARNING_ON_LABEL : LEARNING_OFF_LABEL}
            </button>
          </div>
          <form
            aria-label="Where I am reached"
            onSubmit={(event) => {
              event.preventDefault();
              send(() =>
                request<Preferences>(REACH_API_PATH, { method: "POST", body: reachBody(draft) }),
              );
            }}
          >
            <h3>Where you are told</h3>
            {saved.channels.length === 0 ? (
              <p className="note">{NO_CHANNELS}</p>
            ) : (
              <>
                <label>
                  Reached on first
                  <select
                    value={draft.primary}
                    onChange={(event) => {
                      setDraft({ ...draft, primary: event.target.value });
                    }}
                  >
                    <option value="">{NOT_SET}</option>
                    {saved.channels.map((one) => (
                      <option key={one.channel} value={one.channel}>
                        {one.channel}
                      </option>
                    ))}
                  </select>
                </label>
                {saved.channels.map((one) => (
                  <fieldset key={one.channel}>
                    <legend>{`${one.channel} tells me`}</legend>
                    {saved.notice_kinds.map((kind) => (
                      <label key={kind}>
                        <input
                          type="checkbox"
                          checked={ticked(draft, one.channel, kind)}
                          onChange={(event) => {
                            setDraft(toggled(draft, one.channel, kind, event.target.checked));
                          }}
                        />
                        {kind}
                      </label>
                    ))}
                  </fieldset>
                ))}
              </>
            )}
            <label>
              An approval waits for me on
              <select
                value={draft.approvalRoute}
                onChange={(event) => {
                  setDraft({ ...draft, approvalRoute: event.target.value });
                }}
              >
                <option value="">Wherever it can be answered</option>
                {saved.approval_choices.map((one) => (
                  <option key={one} value={one}>
                    {one}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className="button" disabled={busy}>
              {SAVE_REACH_LABEL}
            </button>
          </form>
          <form
            aria-label="Quiet hours"
            onSubmit={(event) => {
              event.preventDefault();
              send(() =>
                request<Preferences>(QUIET_API_PATH, { method: "POST", body: { start, end } }),
              );
            }}
          >
            <h3>Quiet hours</h3>
            <label>
              From
              <input
                type="time"
                value={start}
                onChange={(event) => {
                  setStart(event.target.value);
                }}
              />
            </label>
            <label>
              Until
              <input
                type="time"
                value={end}
                onChange={(event) => {
                  setEnd(event.target.value);
                }}
              />
            </label>
            <p className="note">{`Held: ${saved.quiet_applies_to.join(" and ")}. ${saved.approvals_are_never_held}`}</p>
            <button type="submit" className="button" disabled={busy || start === "" || end === ""}>
              {SAVE_QUIET_LABEL}
            </button>
            {saved.quiet === null ? null : (
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => {
                  send(() => request<Preferences>(QUIET_API_PATH, { method: "POST", body: {} }));
                }}
              >
                {CLEAR_QUIET_LABEL}
              </button>
            )}
          </form>
          {saved.ignored.length === 0 ? null : (
            <p className="note">{`Not in force, because it could not be read: ${saved.ignored.join(", ")}.`}</p>
          )}
        </>
      )}
    </section>
  );
}
