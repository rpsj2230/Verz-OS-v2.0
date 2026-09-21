/**
 * Referred to me: the sensitive questions routed to the person reading, as notes that somebody
 * asked, and the one act of marking each handled.
 *
 * An agent does not answer a question on a sensitive topic. The asker is told one sentence
 * whatever the topic, and a note goes to the person named for it on the Compliance screen. This is
 * where that person reads their notes, so it sits under Use beside their own work rather than under
 * Govern: being named for grievances is not an administrative grant, and the route asks for none.
 *
 * **There is no question to show, and the page shows nothing in its place.** A referral records who
 * asked, when and about which topic; what they wrote was never stored, and a column for it, even
 * empty, would read as something withheld rather than something that does not exist.
 *
 * **Marking one handled is confirmed**, because it cannot be undone from here and it is the record
 * that the person was contacted. The route answers with the list as it now stands, and the page
 * reads it again so what is drawn is what is stored.
 *
 * Imported statically rather than split: it mounts neither heavy library and no stylesheet.
 *
 * Task ids: M24.2.2
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { when } from "./artifactsQuery";
import { REFERRALS_API_PATH, handledApiPath, referralState, type Referral, type ReferralsAnswer } from "./referralsQuery";

export const REFERRALS_HEADING = "Referred to me";
export const REFERRALS_CRUMB = "Use › Referred to me";
export const REFERRALS_LEDE =
  "Notes that somebody asked about a sensitive topic you are named for. What they wrote is not " +
  "kept; contact them directly, outside their reporting line.";

export const READING_REFERRALS = "Reading what has been referred to you.";
export const NOTHING_REFERRED = "Nothing has been referred to you.";
export const REFERRALS_CAPTION = "Questions referred to you";
export const HANDLED_LABEL = "Mark handled";
export const LEAVE_OPEN = "Leave it open";

export function handledQuestion(one: Referral): string {
  return `Mark the ${one.label} referral from ${one.asked_by}, asked ${when(one.asked_at)}, handled?`;
}
export const HANDLING =
  "It is recorded as handled by you, now, and stays on this list as handled. It cannot be reopened " +
  "from here.";

function ReferralsBody({ onDone }: { readonly onDone: (sentence: string) => void }) {
  const answer = useResource<ReferralsAnswer>(REFERRALS_API_PATH);
  const [pending, setPending] = useState<Referral | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  if (answer.failure !== null) {
    return (
      <section className="card">
        <FailureNotice failure={answer.failure} />
      </section>
    );
  }
  if (answer.data === null) {
    return (
      <p className="note" role="status">
        {READING_REFERRALS}
      </p>
    );
  }
  if (answer.data.referrals.length === 0) {
    return (
      <section className="card">
        <p className="note">{NOTHING_REFERRED}</p>
      </section>
    );
  }

  return (
    <section className="card">
      {failure === null ? null : <FailureNotice failure={failure} />}
      {pending === null ? null : (
        <ConfirmAction
          question={handledQuestion(pending)}
          consequence={HANDLING}
          confirmLabel={HANDLED_LABEL}
          cancelLabel={LEAVE_OPEN}
          busy={busy}
          onConfirm={() => {
            const chosen = pending;
            setBusy(true);
            void (async () => {
              const result = await request<unknown>(handledApiPath(chosen.referral_id), { method: "POST" });
              setBusy(false);
              setPending(null);
              if (!result.ok) {
                setFailure(result.failure);
                return;
              }
              setFailure(null);
              onDone(`The ${chosen.label} referral from ${chosen.asked_by} is marked handled.`);
            })();
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}
      <div className="grid__scroll">
        <table className="grid__table" aria-label={REFERRALS_CAPTION}>
          <thead>
            <tr>
              <th scope="col">Topic</th>
              <th scope="col">Asked by</th>
              <th scope="col">Asked</th>
              <th scope="col">Where it stands</th>
              <th scope="col">Control</th>
            </tr>
          </thead>
          <tbody>
            {answer.data.referrals.map((one) => (
              <tr key={one.referral_id}>
                <td>{one.label}</td>
                <td>
                  <code>{one.asked_by}</code>
                </td>
                <td>{when(one.asked_at)}</td>
                <td>{referralState(one, when)}</td>
                <td>
                  {one.handled_at !== null ? null : (
                    <button
                      type="button"
                      className="button"
                      disabled={busy || pending !== null}
                      aria-label={`${HANDLED_LABEL}: ${one.label}, from ${one.asked_by}`}
                      onClick={() => {
                        setFailure(null);
                        setPending(one);
                      }}
                    >
                      {HANDLED_LABEL}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function Referrals() {
  // A counter rather than a boolean, so two marks in a row read the list twice. Never drawn.
  const [generation, setGeneration] = useState(0);
  const [done, setDone] = useState<string | null>(null);
  const onDone = useCallback((sentence: string) => {
    setDone(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{REFERRALS_CRUMB}</p>
      <h1>{REFERRALS_HEADING}</h1>
      <p className="lede">{REFERRALS_LEDE}</p>
      {done === null ? null : (
        <p className="note" role="status">
          {done}
        </p>
      )}
      <ReferralsBody key={generation} onDone={onDone} />
    </article>
  );
}
