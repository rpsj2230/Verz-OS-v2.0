/**
 * Prompts: the system instructions every agent is given, shown and never editable, and each
 * agent's own instructions, which an administrator can replace or give back to the template.
 *
 * Under Govern, beside the agent screens, because an agent's instructions are part of what an
 * agent is. An edit is written in a form, checked for length before it can be sent, confirmed with
 * what will happen from the next request, and followed by a fresh read so the page shows what the
 * install now holds. Every other refusal, a substitution point the prompt builder would refuse, an
 * edit somebody else made first, the feature switched off, is the API's own sentence.
 *
 * Task ids: M27.8.9
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
import {
  CANCEL,
  EDIT,
  editConsequence,
  EDITING_SWITCHED_OFF,
  editPath,
  editQuestion,
  GIVE_BACK,
  giveBackConsequence,
  giveBackPath,
  giveBackQuestion,
  HOUSE_RULES_HEADING,
  KEEP_IT,
  LENGTHS_HEADING,
  lengthProblem,
  NO_AGENTS,
  NO_MODEL_IS_CALLED_YET,
  EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL,
  PROMPTS_API_PATH,
  PROMPTS_CRUMB,
  PROMPTS_LABEL,
  PROMPTS_LEDE,
  READING_PROMPTS,
  readPrompts,
  SAVE,
  setWords,
  SYSTEM_HEADING,
  SYSTEM_INSTRUCTIONS_ARE_PRODUCT_TEXT,
  TEMPLATE_INSTRUCTIONS,
  THE_BRAIN_COULD_NOT_BE_REACHED,
  UNREADABLE_ANSWER,
  type AgentInstructions,
  type PromptsBody,
} from "./promptsQuery";
import { when } from "./sessionsQuery";

function Failure({ failure }: { readonly failure: ApiFailure }) {
  return (
    <Notice
      title={failure.status === 0 ? THE_BRAIN_COULD_NOT_BE_REACHED : SOMETHING_DID_NOT_WORK}
      traceId={failure.traceId}
    >
      <p>{failure.message}</p>
    </Notice>
  );
}

function SystemInstructions({ body }: { readonly body: PromptsBody }) {
  return (
    <section className="card" aria-labelledby="prompts-system">
      <h2 id="prompts-system">{SYSTEM_HEADING}</h2>
      <h3>{HOUSE_RULES_HEADING}</h3>
      <ol>
        {body.house_rules.map((rule) => (
          <li key={rule}>{rule}</li>
        ))}
      </ol>
      <h3>{LENGTHS_HEADING}</h3>
      <ul>
        {body.output_lengths.map((one) => (
          <li key={one.name}>
            <code>{one.name}</code> {one.instruction}
          </li>
        ))}
      </ul>
      {body.system_instructions_are_product_text === false ? null : (
        <p className="note">{SYSTEM_INSTRUCTIONS_ARE_PRODUCT_TEXT}</p>
      )}
    </section>
  );
}

/** Instructions as written: one paragraph per line, so a line break a person typed is kept. */
function Lines({ text }: { readonly text: string }) {
  return (
    <>
      {text.split(/\r?\n/).map((line, index) => (
        // The position is the identity: two identical lines are two lines.
        <p key={`${String(index)}:${line}`}>{line}</p>
      ))}
    </>
  );
}

type Pending =
  | { readonly kind: "edit"; readonly row: AgentInstructions; readonly text: string }
  | { readonly kind: "give-back"; readonly row: AgentInstructions };

function AgentCard({
  row,
  maxChars,
  busy,
  onAsk,
}: {
  readonly row: AgentInstructions;
  readonly maxChars: number;
  readonly busy: boolean;
  readonly onAsk: (pending: Pending) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const problem = draft === null ? null : lengthProblem(draft, maxChars);
  const fieldId = `instructions-${row.agent_id}`;

  return (
    <section className="card" aria-labelledby={`agent-${row.agent_id}`}>
      <h2 id={`agent-${row.agent_id}`}>
        {row.display_name} <code>{row.agent_id}</code>
      </h2>
      {row.department ? <p className="note">{row.department}</p> : null}
      <p className="note">{setWords(row, when)}</p>
      {draft === null ? (
        <Lines text={row.instructions} />
      ) : (
        <form
          className="form"
          aria-label={`${EDIT}: ${row.display_name}`}
          onSubmit={(event) => {
            event.preventDefault();
            if (problem === null) {
              onAsk({ kind: "edit", row, text: draft });
            }
          }}
        >
          <label className="control-label" htmlFor={fieldId}>
            Instructions
          </label>
          <textarea
            id={fieldId}
            className="form-control"
            rows={8}
            value={draft}
            aria-describedby={`${fieldId}-count`}
            onChange={(event) => {
              setDraft(event.target.value);
            }}
          />
          <p className="note" id={`${fieldId}-count`}>
            {problem ?? `${String(draft.trim().length)} of ${String(maxChars)} characters.`}
          </p>
          <div className="form-actions">
            <button
              type="button"
              className="button"
              onClick={() => {
                setDraft(null);
              }}
            >
              {CANCEL}
            </button>{" "}
            <button type="submit" className="button" disabled={busy || problem !== null}>
              {SAVE}
            </button>
          </div>
        </form>
      )}
      {row.overridden && row.template_instructions ? (
        <details>
          <summary>{TEMPLATE_INSTRUCTIONS}</summary>
          <Lines text={row.template_instructions} />
        </details>
      ) : null}
      {draft === null ? (
        <div className="form-actions">
          {row.editable ? (
            <button
              type="button"
              className="button"
              disabled={busy}
              aria-label={`${EDIT}: ${row.display_name}`}
              onClick={() => {
                setDraft(row.instructions);
              }}
            >
              {EDIT}
            </button>
          ) : null}{" "}
          {row.installed && row.overridden && row.effective_hash ? (
            <button
              type="button"
              className="button"
              disabled={busy}
              aria-label={`${GIVE_BACK}: ${row.display_name}`}
              onClick={() => {
                onAsk({ kind: "give-back", row });
              }}
            >
              {GIVE_BACK}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function PromptList({ onDone }: { readonly onDone: (sentence: string) => void }) {
  const answer = useResource<unknown>(PROMPTS_API_PATH);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const send = useCallback(
    (asked: Pending) => {
      setBusy(true);
      void (async () => {
        const result =
          asked.kind === "edit"
            ? await request<unknown>(editPath(asked.row.agent_id), {
                method: "POST",
                body: { instructions: asked.text, expected_hash: asked.row.effective_hash ?? "" },
              })
            : await request<unknown>(giveBackPath(asked.row.agent_id), {
                method: "POST",
                body: { expected_hash: asked.row.effective_hash ?? "" },
              });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onDone(
          asked.kind === "edit"
            ? `${asked.row.display_name}'s instructions were replaced. It is given them from the next request.`
            : `${asked.row.display_name}'s instructions were given back to its template.`,
        );
      })();
    },
    [onDone],
  );

  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_PROMPTS}
      </p>
    );
  }
  if (answer.failure) {
    return <Failure failure={answer.failure} />;
  }
  const body = readPrompts(answer.data);
  if (body === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }

  return (
    <>
      <SystemInstructions body={body} />
      {failure === null ? null : <Failure failure={failure} />}
      {pending === null ? null : (
        <ConfirmAction
          question={pending.kind === "edit" ? editQuestion(pending.row) : giveBackQuestion(pending.row)}
          consequence={pending.kind === "edit" ? editConsequence(pending.row) : giveBackConsequence(pending.row)}
          confirmLabel={pending.kind === "edit" ? SAVE : GIVE_BACK}
          cancelLabel={KEEP_IT}
          busy={busy}
          onConfirm={() => {
            send(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}
      {body.editing_switched_on ? null : <p className="note">{EDITING_SWITCHED_OFF}</p>}
      {body.no_model_is_called_yet === false ? null : <p className="note">{NO_MODEL_IS_CALLED_YET}</p>}
      {body.every_change_is_in_the_audit_trail === false ? null : (
        <p className="note">{EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL}</p>
      )}
      {body.agents.length === 0 ? (
        <section className="card">
          <p className="note">{NO_AGENTS}</p>
        </section>
      ) : (
        body.agents.map((row) => (
          <AgentCard
            key={row.agent_id}
            row={row}
            maxChars={body.max_chars}
            busy={busy}
            onAsk={(asked) => {
              setFailure(null);
              setPending(asked);
            }}
          />
        ))
      )}
    </>
  );
}

export function Prompts() {
  // A counter rather than a boolean, so two edits in a row remount twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [done, setDone] = useState<string | null>(null);
  const onDone = useCallback((sentence: string) => {
    setDone(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{PROMPTS_CRUMB}</p>
      <h1>{PROMPTS_LABEL}</h1>
      <p className="lede">{PROMPTS_LEDE}</p>
      {done === null ? null : (
        <p className="note" role="status">
          {done}
        </p>
      )}
      <PromptList key={generation} onDone={onDone} />
    </article>
  );
}
