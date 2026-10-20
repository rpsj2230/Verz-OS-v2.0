/**
 * A person's own skills, in My workspace: the ones they wrote, pasted or brought in, where each
 * stands, and offering one to the department's library.
 *
 * Every row is the API's answer for the person asking (`brain.member_skill_routes`) and draws what
 * it was sent, including the sentence saying what the skill can do now. A skill is the person's
 * alone until they offer it, and offering it is confirmed, because a named person is then asked to
 * read it and it cannot be taken back. Nothing here approves a skill or puts one on an agent. A
 * blank form says what to fill in before anything is sent, and the switch being off is the API's
 * own sentence in place of the form.
 *
 * Task ids: M40.3.2.1, M40.3.2.2, M40.3.2.3
 */

import { useCallback, useId, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { when } from "../pages/artifactsQuery";
import {
  EMPTY_DRAFT,
  IMPORT_MY_SKILL_API_PATH,
  MY_SKILLS_API_PATH,
  WAYS,
  importBody,
  offerMySkillApiPath,
  whatToFill,
  writeBody,
  type MySkill,
  type MySkillsBody,
  type SkillDraft,
  type Way,
} from "../pages/mySkillsQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { ConfirmAction } from "./ConfirmAction";
import { EmptyList } from "./kit/states";

export const SKILLS_CAPTION = "My skills";
export const ADD_LABEL = "Add this skill";
export const OFFER_LABEL = "Offer to the department";
export const KEEP_PRIVATE_LABEL = "Keep it to myself";
export const OFFER_QUESTION = "Offer this skill to the department?";
export const OFFER_CONSEQUENCE =
  "A named person will be asked to read it and approve or reject it, and you cannot take the " +
  "offer back. Nothing runs it until they approve it. It is recorded in the audit ledger.";
export const NO_SKILLS = "You have not added a skill of your own.";
export const MORE_SKILLS = "There are more than are shown here.";

const ORIGIN_WORDS: Readonly<Record<string, string>> = {
  studio: "written here",
  repository: "from a repository",
  url: "from an address",
};

function Reading() {
  return (
    <p className="note" role="status">
      Reading your skills.
    </p>
  );
}

function AddForm({ onAdded }: { readonly onAdded: () => void }) {
  const ids = useId();
  const [draft, setDraft] = useState<SkillDraft>(EMPTY_DRAFT);
  const [said, setSaid] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const fillId = `${ids}-fill`;

  const send = useCallback(() => {
    const missing = whatToFill(draft);
    setSaid(missing);
    if (missing !== "") {
      return;
    }
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result =
        draft.way === "write"
          ? await request<unknown>(MY_SKILLS_API_PATH, { method: "POST", body: writeBody(draft) })
          : await request<unknown>(IMPORT_MY_SKILL_API_PATH, {
              method: "POST",
              body: importBody(draft),
            });
      setBusy(false);
      if (result.ok) {
        setDraft(EMPTY_DRAFT);
        onAdded();
        return;
      }
      setFailure(result.failure);
    })();
  }, [draft, onAdded]);

  const field = (name: keyof SkillDraft, label: string, long = false) => (
    <label>
      {label}
      {long ? (
        <textarea
          rows={10}
          value={draft[name]}
          aria-invalid={said !== ""}
          aria-describedby={said === "" ? undefined : fillId}
          onChange={(event) => {
            setDraft({ ...draft, [name]: event.target.value });
          }}
        />
      ) : (
        <input
          type="text"
          value={draft[name]}
          aria-invalid={said !== ""}
          aria-describedby={said === "" ? undefined : fillId}
          onChange={(event) => {
            setDraft({ ...draft, [name]: event.target.value });
          }}
        />
      )}
    </label>
  );

  return (
    <form
      aria-label="Add a skill of my own"
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
    >
      <h3>Add a skill</h3>
      {failure === null ? null : <FailureNotice failure={failure} />}
      <label>
        How
        <select
          value={draft.way}
          onChange={(event) => {
            setSaid("");
            setDraft({ ...draft, way: event.target.value as Way });
          }}
        >
          {WAYS.map((one) => (
            <option key={one.way} value={one.way}>
              {one.label}
            </option>
          ))}
        </select>
      </label>
      {draft.way === "write" ? field("text", "The skill, as a SKILL.md", true) : null}
      {draft.way === "address" ? field("url", "Address (https)") : null}
      {draft.way === "repository" ? (
        <>
          {field("repository", "Repository (owner/name)")}
          {field("commit", "Commit (all forty characters)")}
          {field("path", "Folder holding the SKILL.md (blank for the top)")}
        </>
      ) : null}
      {said === "" ? null : (
        <p id={fillId} role="alert" className="note">
          {said}
        </p>
      )}
      <button type="submit" className="button" disabled={busy}>
        {ADD_LABEL}
      </button>
    </form>
  );
}

export function MySkills() {
  const [version, setVersion] = useState(0);
  const answer = useResource<MySkillsBody>(MY_SKILLS_API_PATH, version);
  const [offering, setOffering] = useState<MySkill | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const offer = useCallback((one: MySkill) => {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(offerMySkillApiPath(one.digest), { method: "POST" });
      setBusy(false);
      setOffering(null);
      if (result.ok) {
        setVersion((current) => current + 1);
        return;
      }
      setFailure(result.failure);
    })();
  }, []);

  return (
    <section className="card">
      <h2>{SKILLS_CAPTION}</h2>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {offering === null ? null : (
        <ConfirmAction
          question={OFFER_QUESTION}
          consequence={OFFER_CONSEQUENCE}
          confirmLabel={OFFER_LABEL}
          cancelLabel={KEEP_PRIVATE_LABEL}
          busy={busy}
          onConfirm={() => {
            offer(offering);
          }}
          onCancel={() => {
            setOffering(null);
          }}
        />
      )}
      {answer.failure ? (
        <FailureNotice failure={answer.failure} />
      ) : answer.data === null ? (
        <Reading />
      ) : (
        <>
          {answer.data.skills.length === 0 ? (
            <EmptyList
              compact
              title={NO_SKILLS}
              adds="A skill you write, paste or bring in is listed here, and stays yours until you offer it."
              by={["member"]}
            />
          ) : (
            <ul aria-label={SKILLS_CAPTION}>
              {answer.data.skills.map((one) => (
                <li key={one.digest}>
                  <strong>{one.name}</strong>
                  {` ${one.version}, ${ORIGIN_WORDS[one.origin] ?? one.origin}, ${one.location}. `}
                  {one.offered && one.offered_at ? `Offered ${when(one.offered_at)}. ` : ""}
                  {one.standing}{" "}
                  {one.may_offer ? (
                    <button
                      type="button"
                      className="button"
                      aria-label={`${OFFER_LABEL}: ${one.name} ${one.version}`}
                      disabled={busy}
                      onClick={() => {
                        setFailure(null);
                        setOffering(one);
                      }}
                    >
                      {OFFER_LABEL}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {answer.data.more ? <p className="note">{MORE_SKILLS}</p> : null}
          {answer.data.may_add ? (
            <AddForm
              onAdded={() => {
                setVersion((current) => current + 1);
              }}
            />
          ) : (
            <p className="note">{answer.data.unavailable}</p>
          )}
        </>
      )}
    </section>
  );
}
