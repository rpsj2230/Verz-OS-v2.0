/**
 * Requirement checks: every requirement the owner asked for, by area, and what a person saw each do
 * on this install.
 *
 * Four tasks ask for the same thing of four areas, permissions, departments, models and
 * observability: every requirement demonstrated on an install by a person, and each check recorded
 * against the requirement it proves. This is where that happens. The tabs are the register's areas,
 * each saying where its checks stand and which task asks for them; the table is one area's
 * requirements in the owner's words with the newest check; and the form records a check as the
 * person signed in, against the release this install runs.
 *
 * **A check supersedes and never edits.** Recording "failed" after "passed" leaves both in the
 * table; the screen shows the newest, and the API keeps the rest. Nothing here removes a check.
 *
 * Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6
 */

import { useCallback, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { FailureNotice } from "../ui/FailureNotice";
import { when } from "./auditQuery";
import {
  AREA_PARAMETER,
  CHECKS_API_PATH,
  CHECKS_LABEL,
  CHECKS_PATH,
  DRAFT_PROBLEMS,
  EMPTY_DRAFT,
  NOTE_CHARS,
  OUTCOMES,
  OUTCOME_WORDS,
  checkBody,
  checkLine,
  checksApiPath,
  draftProblems,
  readChecks,
  standing,
  type CheckDraft,
  type ChecksBody,
} from "./requirementChecksQuery";

export const CHECKS_HEADING = CHECKS_LABEL;
export const CHECKS_CRUMB = "Install › Requirement checks";
export const CHECKS_LEDE =
  "Every requirement the owner asked for, in the owner's words. Check each one on this install and " +
  "record what you saw, so every area can show which requirements were seen working.";
export const READING_CHECKS = "Reading the register and the checks.";
export const NOT_A_BODY = "The answer about requirement checks was not in a shape this screen can read.";
export const NOT_CHECKED = "Not checked yet";
export const RECORD_HEADING = "Record a check";
export const RECORD_LABEL = "Record the check";
export const RECORDED = "The check was recorded.";
export const AREAS_LABEL = "Areas of the register";
export const REQUIREMENTS_LABEL = "Requirements in this area";

function Areas({ body }: { readonly body: ChecksBody }) {
  return (
    <nav aria-label={AREAS_LABEL}>
      <ul className="roster">
        {body.areas.map((area) => (
          <li key={area.area}>
            {area.area === body.area ? (
              <strong>{area.area}</strong>
            ) : (
              <Link to={`${CHECKS_PATH}?${new URLSearchParams({ [AREA_PARAMETER]: area.area }).toString()}`}>
                {area.area}
              </Link>
            )}{" "}
            <span className="note">
              {standing(area)}
              {area.proves === null || area.proves === undefined ? "" : `, for ${area.proves}`}
            </span>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Record({
  body,
  onRecorded,
}: {
  readonly body: ChecksBody;
  readonly onRecorded: () => void;
}) {
  const [draft, setDraft] = useState<CheckDraft>(EMPTY_DRAFT);
  const [problems, setProblems] = useState<readonly (keyof typeof DRAFT_PROBLEMS)[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [said, setSaid] = useState("");

  const send = useCallback(
    (ready: CheckDraft) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(CHECKS_API_PATH, { method: "POST", body: checkBody(ready) });
        setBusy(false);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        setDraft(EMPTY_DRAFT);
        setSaid(RECORDED);
        onRecorded();
      })();
    },
    [onRecorded],
  );

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const missing = draftProblems(draft);
    setProblems(missing);
    setSaid("");
    if (missing.length > 0) {
      return;
    }
    send(draft);
  };

  return (
    <section className="card">
      <h2>{RECORD_HEADING}</h2>
      <p className="note">{body.told}</p>
      <form className="form" aria-label={RECORD_HEADING} onSubmit={onSubmit} noValidate>
        <label className="control-label">
          Requirement{" "}
          <select
            className="form-control"
            value={draft.requirementId}
            onChange={(event) => setDraft({ ...draft, requirementId: event.target.value })}
          >
            <option value="">Choose one</option>
            {body.requirements.map((one) => (
              <option key={one.id} value={one.id}>
                {one.id}
              </option>
            ))}
          </select>
        </label>
        {problems.includes("requirementId") ? <p className="note">{DRAFT_PROBLEMS.requirementId}</p> : null}
        <label className="control-label">
          Outcome{" "}
          <select
            className="form-control"
            value={draft.outcome}
            onChange={(event) => setDraft({ ...draft, outcome: event.target.value })}
          >
            <option value="">Choose one</option>
            {OUTCOMES.map((one) => (
              <option key={one} value={one}>
                {OUTCOME_WORDS[one]}
              </option>
            ))}
          </select>
        </label>
        {problems.includes("outcome") ? <p className="note">{DRAFT_PROBLEMS.outcome}</p> : null}
        <label className="control-label">
          What you did and saw{" "}
          <textarea
            className="form-control"
            maxLength={NOTE_CHARS}
            value={draft.note}
            onChange={(event) => setDraft({ ...draft, note: event.target.value })}
          />
        </label>
        {problems.includes("note") ? <p className="note">{DRAFT_PROBLEMS.note}</p> : null}
        <button type="submit" className="button" disabled={busy}>
          {RECORD_LABEL}
        </button>
      </form>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {said === "" ? null : (
        <p className="note" role="status">
          {said}
        </p>
      )}
    </section>
  );
}

export function RequirementChecks() {
  const [search] = useSearchParams();
  const area = search.get(AREA_PARAMETER);
  const [version, setVersion] = useState(0);
  // A recorded check bumps the version, which asks again, so the table shows the newest check.
  const answer = useResource<unknown>(checksApiPath(area), version);
  const onRecorded = useCallback(() => setVersion((one) => one + 1), []);

  let content;
  if (answer.failure) {
    content = <FailureNotice failure={answer.failure} />;
  } else if (answer.busy) {
    content = (
      <p className="note" role="status">
        {READING_CHECKS}
      </p>
    );
  } else {
    const body = readChecks(answer.data);
    content =
      body === null ? (
        <p className="note">{NOT_A_BODY}</p>
      ) : (
        <>
          <Areas body={body} />
          <section className="card">
            <h2>{body.area ?? CHECKS_LABEL}</h2>
            <div className="grid__scroll">
              <table className="grid__table" aria-label={REQUIREMENTS_LABEL}>
                <thead>
                  <tr>
                    <th scope="col">Requirement</th>
                    <th scope="col">What the owner asked for</th>
                    <th scope="col">Newest check</th>
                  </tr>
                </thead>
                <tbody>
                  {body.requirements.map((one) => (
                    <tr key={one.id}>
                      <td>
                        <code>{one.id}</code>
                      </td>
                      <td>{one.requirement}</td>
                      <td>
                        {one.latest === null || one.latest === undefined ? (
                          NOT_CHECKED
                        ) : (
                          <>
                            {checkLine(one.latest, when)}
                            <p className="note">{one.latest.note}</p>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <Record body={body} onRecorded={onRecorded} />
        </>
      );
  }

  return (
    <article className="page">
      <p className="note">{CHECKS_CRUMB}</p>
      <h1>{CHECKS_HEADING}</h1>
      <p className="lede">{CHECKS_LEDE}</p>
      {content}
    </article>
  );
}
