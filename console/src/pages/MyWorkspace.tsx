/**
 * My workspace: what a person has asked, what they can call, what has been learnt about them, what
 * they keep, and what they can ask about. For a reader who administers nothing.
 *
 * `docs/screens.html` SCREEN 12 is the design of record, and this is its layout in its order: four
 * figures across the top (questions this month, agents I can call, my budget, learned about me),
 * then My agents beside What it learned about me, then Knowledge I own beside Connected accounts,
 * then What I can ask about. Each card's title is the design's, one column on a phone.
 *
 * **Every figure is the person's own, and the page asks nothing that could be about somebody
 * else.** `brain.mine_routes` takes no parameter naming a person. It opens on the member grant,
 * which `brain.member.shell` refuses to share with any administrative screen, so a person holding
 * nothing administrative reaches this page and a person holding only administrative grants does
 * not. A 404 is the API saying this caller may not open it, and the page does not explain further.
 *
 * **What the design draws and nothing records is a sentence where the design draws it.** The
 * corrections under the questions figure, the Undo all control, the Verified and Used 30d columns
 * of the knowledge card, and the connected accounts are each the API's own sentence, because
 * nothing on an install records them. `brain.console.own_things` names the decisions each would
 * need.
 *
 * **What it learned about me can be edited and forgotten here** (M16.4.2): each item has Edit,
 * which keeps what the person writes instead, and Forget, confirmed in words that say the record
 * stays. Both are the API's routes for the person's own memories, and the page is read again after
 * either, so what is shown is what the next answer uses.
 *
 * Imported statically rather than split: it mounts neither heavy library and no stylesheet.
 *
 * Task ids: M27.7.28, M16.4.2
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { MyChannels } from "../components/MyChannels";
import { ConfirmDialog } from "../components/kit";
import { Button } from "../components/ui/button";
import { FailureNotice } from "../ui/FailureNotice";
import { when } from "./artifactsQuery";
import {
  EDIT_API_PATH,
  FORGET_API_PATH,
  PROVISION_WORDS,
  WORKSPACE_API_PATH,
  editBody,
  forgetBody,
  monthly,
  ownAgents,
  readBudget,
  spentOf,
  wasRead,
  readChanged,
  whereItRuns,
  type Learned,
  type Workspace,
} from "./myWorkspaceQuery";

export const WORKSPACE_HEADING = "My workspace";
export const WORKSPACE_CRUMB = "Use › My workspace";
export const WORKSPACE_LEDE =
  "What you asked, the agents you can call, what has been learnt about you, and what you keep. " +
  "Everything on this page is yours or already visible to you, and it shows nothing your access " +
  "would not already return in an answer.";

export const READING_WORKSPACE = "Reading your workspace.";

/** Under a refusal: which grant opens the page, which is the same sentence for everybody. */
export const OPENS_ON_THE_MEMBER_GRANT =
  "This page opens for anybody holding the member grant, and for nobody else, whatever else they " +
  "hold. If you expected to see it, ask your department administrator for it.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

export const NO_AGENTS = "There are no agents you can call.";
export const NO_CEILING = "No budget of your own is set.";
export const NOTHING_LEARNED = "Nothing learnt about you is shown.";
export const NO_ITEMS = "You do not look after any knowledge items.";
export const MORE_ITEMS = "You look after more items than this page reads at once.";

export const EDIT_LABEL = "Edit";
export const FORGET_LABEL = "Forget";
export const SAVE_LABEL = "Save";
export const CANCEL_LABEL = "Cancel";
export const KEEP_IT = "Keep it";
export const WHAT_IT_SHOULD_SAY = "What it should say";
export const FORGET_CONSEQUENCE =
  "It stops being used in your answers at once. The record that it was learnt stays, and if it " +
  "replaced something earlier, the earlier one is used again.";

/** The longest statement the API keeps: `brain.memory.turn.MAX_STATEMENT_CHARS`. */
export const STATEMENT_CHARS = 280;

export const AGENTS_CAPTION = "Agents I can call";
export const ITEMS_CAPTION = "Knowledge I own";
export const LEARNED_CAPTION = "What it learned about me";

function Figures({ workspace }: { readonly workspace: Workspace }) {
  const budget = readBudget(workspace);
  const month = wasRead(budget) ? monthly(budget.panel) : null;
  return (
    <section className="card">
      <h2>At a glance</h2>
      <dl className="fields" aria-label="My workspace at a glance">
        <div className="fields__row">
          <dt>Questions this month</dt>
          <dd>
            <span>{String(workspace.asked.questions)}</span>
            <p className="note">{workspace.asked.corrections}</p>
          </dd>
        </div>
        <div className="fields__row">
          <dt>Agents I can call</dt>
          <dd>
            <span>{String(workspace.agents.length)}</span>
            <p className="note">{`${String(ownAgents(workspace.agents))} of them your own`}</p>
          </dd>
        </div>
        <div className="fields__row">
          <dt>My budget</dt>
          <dd>
            {!wasRead(budget) ? (
              <p className="note">{budget.unread}</p>
            ) : month === null ? (
              <p className="note">{NO_CEILING}</p>
            ) : (
              <span>{spentOf(month)}</span>
            )}
          </dd>
        </div>
        <div className="fields__row">
          <dt>Learned about me</dt>
          <dd>
            <span>{String(workspace.learned.length)}</span>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function MyAgents({ workspace }: { readonly workspace: Workspace }) {
  return (
    <section className="card">
      <h2>My agents</h2>
      {workspace.agents.length === 0 ? (
        <p className="note">{NO_AGENTS}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table" aria-label={AGENTS_CAPTION}>
            <thead>
              <tr>
                <th scope="col">Agent</th>
                <th scope="col">Source</th>
                <th scope="col">Where it runs</th>
                <th scope="col">Used 30d</th>
              </tr>
            </thead>
            <tbody>
              {workspace.agents.map((one) => (
                <tr key={one.agent_id}>
                  <td>
                    <code>{one.agent_id}</code>
                  </td>
                  <td>{PROVISION_WORDS[one.provision] ?? one.provision}</td>
                  <td>{whereItRuns(one)}</td>
                  <td>{String(one.uses)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** What the last forget or edit came to, held above the card so a re-read keeps it on screen. */
interface Outcome {
  readonly said: string;
  readonly failure: ApiFailure | null;
}

const NO_OUTCOME: Outcome = { said: "", failure: null };

function WhatItLearned({
  workspace,
  outcome,
  onOutcome,
}: {
  readonly workspace: Workspace;
  readonly outcome: Outcome;
  readonly onOutcome: (outcome: Outcome, reread: boolean) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [forgetting, setForgetting] = useState<Learned | null>(null);
  const [busy, setBusy] = useState(false);

  const send = useCallback(
    (path: string, body: unknown) => {
      setBusy(true);
      onOutcome(NO_OUTCOME, false);
      void (async () => {
        const result = await request<unknown>(path, { method: "POST", body });
        setBusy(false);
        setForgetting(null);
        setEditing(null);
        if (!result.ok) {
          onOutcome({ said: "", failure: result.failure }, false);
          return;
        }
        onOutcome({ said: readChanged(result.data).told, failure: null }, true);
      })();
    },
    [onOutcome],
  );

  return (
    <section className="card">
      <h2>{LEARNED_CAPTION}</h2>
      {outcome.said === "" ? null : (
        <p className="note" role="status">
          {outcome.said}
        </p>
      )}
      {outcome.failure === null ? null : <FailureNotice failure={outcome.failure} />}
      {workspace.learned.length === 0 ? (
        <p className="note">{NOTHING_LEARNED}</p>
      ) : (
        <ul aria-label={LEARNED_CAPTION}>
          {workspace.learned.map((one) => (
            <li key={one.memory_id}>
              {editing === one.memory_id ? (
                <form
                  aria-label={`${EDIT_LABEL} ${one.statement}`}
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (draft.trim() !== "") {
                      send(EDIT_API_PATH, editBody(one.memory_id, draft));
                    }
                  }}
                >
                  <label>
                    {WHAT_IT_SHOULD_SAY}
                    <textarea
                      value={draft}
                      maxLength={STATEMENT_CHARS}
                      onChange={(event) => {
                        setDraft(event.target.value);
                      }}
                    />
                  </label>
                  <Button type="submit" size="sm" disabled={busy || draft.trim() === ""}>
                    {SAVE_LABEL}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setEditing(null);
                    }}
                  >
                    {CANCEL_LABEL}
                  </Button>
                </form>
              ) : (
                <strong>{one.statement}</strong>
              )}
              <p className="note">
                {`${one.stated ? "You said this" : "Inferred"}, ${when(one.formed_at)}`}
              </p>
              {editing === one.memory_id ? null : (
                <div>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    aria-label={`${EDIT_LABEL} ${one.statement}`}
                    onClick={() => {
                      setDraft(one.statement);
                      setEditing(one.memory_id);
                    }}
                  >
                    {EDIT_LABEL}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    aria-label={`${FORGET_LABEL} ${one.statement}`}
                    onClick={() => {
                      setForgetting(one);
                    }}
                  >
                    {FORGET_LABEL}
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="note">{workspace.learned_undo}</p>
      <ConfirmDialog
        open={forgetting !== null}
        question={forgetting === null ? "" : `${FORGET_LABEL} "${forgetting.statement}"?`}
        consequence={FORGET_CONSEQUENCE}
        confirmLabel={FORGET_LABEL}
        cancelLabel={KEEP_IT}
        busy={busy}
        onConfirm={() => {
          if (forgetting !== null) {
            send(FORGET_API_PATH, forgetBody(forgetting.memory_id));
          }
        }}
        onCancel={() => {
          setForgetting(null);
        }}
      />
    </section>
  );
}

function KnowledgeIOwn({ workspace }: { readonly workspace: Workspace }) {
  return (
    <section className="card">
      <h2>{ITEMS_CAPTION}</h2>
      {workspace.knowledge.length === 0 ? (
        <p className="note">{NO_ITEMS}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table" aria-label={ITEMS_CAPTION}>
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col">Visible to</th>
              </tr>
            </thead>
            <tbody>
              {workspace.knowledge.map((one) => (
                <tr key={one.item_id}>
                  <td>
                    <code>{one.item_id}</code>
                  </td>
                  <td>
                    <code>{one.department ?? one.level}</code>
                    {one.department === null ? null : <span className="note"> {one.level}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {workspace.knowledge_truncated ? <p className="note">{MORE_ITEMS}</p> : null}
      <p className="note">{workspace.knowledge_not_shown}</p>
    </section>
  );
}

export function MyWorkspace() {
  const [version, setVersion] = useState(0);
  const answer = useResource<Workspace>(WORKSPACE_API_PATH, version);
  const [outcome, setOutcome] = useState<Outcome>(NO_OUTCOME);
  const settled = useCallback((next: Outcome, reread: boolean) => {
    setOutcome(next);
    if (reread) {
      setVersion((count) => count + 1);
    }
  }, []);

  return (
    <article className="page">
      <p className="note">{WORKSPACE_CRUMB}</p>
      <h1>{WORKSPACE_HEADING}</h1>
      <p className="lede">{WORKSPACE_LEDE}</p>

      {answer.failure ? (
        <section className="card">
          <FailureNotice failure={answer.failure}>
            {/*
             * Not said when the API asked for a second factor: that refusal is also a 404, and a
             * note about the member grant under it would send a person looking for a grant they
             * already hold. See `api/errors.THE_SECOND_FACTOR_IS_READ_FROM_ITS_FLAG`.
             */}
            {answer.failure.status === 404 && !answer.failure.secondFactorNeeded ? (
              <p className="note">{OPENS_ON_THE_MEMBER_GRANT}</p>
            ) : null}
          </FailureNotice>
        </section>
      ) : null}

      {answer.busy ? (
        <p className="note" role="status">
          {READING_WORKSPACE}
        </p>
      ) : null}

      {answer.data === null ? null : (
        <>
          <p>{`Signed in as ${answer.data.display_name}.`}</p>
          <Figures workspace={answer.data} />
          <MyAgents workspace={answer.data} />
          <WhatItLearned workspace={answer.data} outcome={outcome} onOutcome={settled} />
          <KnowledgeIOwn workspace={answer.data} />
          <section className="card">
            <h2>Connected accounts</h2>
            <p>{answer.data.accounts}</p>
          </section>
          <section className="card">
            <h2>What I can ask about</h2>
            <p>{answer.data.can_ask_about}</p>
          </section>
          <MyChannels />
        </>
      )}
    </article>
  );
}
