/**
 * Prompts on the shared page kit: the product's own instructions, and each agent's with its edit
 * and its give-back to the template, both confirmed.
 *
 * **The edit form stays on the page, beside the text it replaces**, and says what it accepts and
 * how much of it is used before anything is sent; the API judges the text and its answer's problems
 * are drawn beside the field. Both writes name the configuration digest the page read, so an edit
 * made against instructions somebody else has since changed is refused rather than overwriting it.
 *
 * **What was removed**: each agent's id beside its name, and the template id and the principal id
 * inside "who set these" (all three are in Advanced now); the three notes under the heading are one
 * footer line, and the switched-off note shows only while editing is off.
 *
 * Task ids: M27.8.9, M27.16.1
 */

import { useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  ConfirmDialog,
  EmptyState,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  Note,
  PageHeader,
  SectionCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  CANCEL,
  EDIT,
  editConsequence,
  editPath,
  editQuestion,
  EDITING_SWITCHED_OFF,
  EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL,
  GIVE_BACK,
  giveBackConsequence,
  giveBackPath,
  giveBackQuestion,
  HOUSE_RULES_HEADING,
  instructionsHint,
  KEEP_IT,
  LENGTHS_HEADING,
  lengthProblem,
  NO_AGENTS,
  NO_MODEL_IS_CALLED_YET,
  PROMPTS_API_PATH,
  PROMPTS_LABEL,
  PROMPTS_LEDE,
  READING_PROMPTS,
  readPrompts,
  SAVE,
  setWords,
  SYSTEM_HEADING,
  SYSTEM_INSTRUCTIONS_ARE_PRODUCT_TEXT,
  TEMPLATE_INSTRUCTIONS,
  UNREADABLE_ANSWER,
  type AgentInstructions,
  type PromptsBody,
} from "../promptsQuery";
import { when } from "../sessionsQuery";

export const NO_AGENTS_TITLE = "No agent instructions to show";

/** The name an edit's text is sent under. `expected_hash` is sent too, and no input holds it. */
const INSTRUCTIONS_NAME = "instructions";

type Pending =
  | { readonly kind: "edit"; readonly row: AgentInstructions; readonly text: string }
  | { readonly kind: "give-back"; readonly row: AgentInstructions };

/** Instructions as written: one paragraph per line, so a line break a person typed is kept. */
function Lines({ text }: { readonly text: string }) {
  return (
    <div className="flex flex-col gap-1.5 text-[13px] leading-relaxed text-body [overflow-wrap:anywhere]">
      {text.split(/\r?\n/).map((line, index) => (
        // The position is the identity: two identical lines are two lines.
        <p key={`${String(index)}:${line}`} className="m-0">
          {line}
        </p>
      ))}
    </div>
  );
}

function SystemInstructions({ body }: { readonly body: PromptsBody }) {
  return (
    <SectionCard
      title={SYSTEM_HEADING}
      lede={body.system_instructions_are_product_text === false ? undefined : SYSTEM_INSTRUCTIONS_ARE_PRODUCT_TEXT}
    >
      <h3 className="m-0 text-[13px] font-medium text-ink">{HOUSE_RULES_HEADING}</h3>
      <ol className="m-0 mt-1.5 flex list-decimal flex-col gap-1 pl-5 text-[13px] text-body">
        {body.house_rules.map((rule) => (
          <li key={rule}>{rule}</li>
        ))}
      </ol>
      <h3 className="m-0 mt-3 text-[13px] font-medium text-ink">{LENGTHS_HEADING}</h3>
      <FactList className="mt-1.5">
        {body.output_lengths.map((one) => (
          <Fact key={one.name} label={one.name}>
            {one.instruction}
          </Fact>
        ))}
      </FactList>
    </SectionCard>
  );
}

function AgentCard({
  row,
  maxChars,
  busy,
  problems,
  onAsk,
}: {
  readonly row: AgentInstructions;
  readonly maxChars: number;
  readonly busy: boolean;
  /** What the API refused in this agent's last edit, for the list beside its text. */
  readonly problems: readonly FieldProblem[];
  readonly onAsk: (pending: Pending) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const problem = draft === null ? null : lengthProblem(draft, maxChars);
  const fieldId = `instructions-${row.agent_id}`;
  const lede = [row.department, setWords(row, when)].filter((one) => one !== null && one !== undefined && one !== "").join(". ");
  const actions =
    draft === null ? (
      <>
        {row.editable ? (
          <Button
            size="sm"
            variant="outline"
            className="min-h-11 sm:min-h-8"
            disabled={busy}
            aria-label={`${EDIT}: ${row.display_name}`}
            onClick={() => {
              setDraft(row.instructions);
            }}
          >
            {EDIT}
          </Button>
        ) : null}
        {row.installed && row.overridden && row.effective_hash ? (
          <Button
            size="sm"
            variant="outline"
            className="min-h-11 sm:min-h-8"
            disabled={busy}
            aria-label={`${GIVE_BACK}: ${row.display_name}`}
            onClick={() => {
              onAsk({ kind: "give-back", row });
            }}
          >
            {GIVE_BACK}
          </Button>
        ) : null}
      </>
    ) : undefined;
  return (
    <SectionCard title={row.display_name} lede={lede} action={actions}>
      {draft === null ? (
        <Lines text={row.instructions} />
      ) : (
        <form
          className="flex min-w-0 flex-col gap-2"
          aria-label={`${EDIT}: ${row.display_name}`}
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (problem === null) {
              onAsk({ kind: "edit", row, text: draft });
            }
          }}
        >
          <Label htmlFor={fieldId}>Instructions</Label>
          <p id={`${fieldId}-hint`} className="m-0 text-[12.5px] leading-snug text-dim">
            {instructionsHint(maxChars)}
          </p>
          <Textarea
            id={fieldId}
            name={INSTRUCTIONS_NAME}
            rows={8}
            value={draft}
            {...problemAttributes(problems, fieldId, INSTRUCTIONS_NAME, `${fieldId}-count`)}
            onChange={(event) => {
              setDraft(event.target.value);
            }}
          />
          <FieldProblems problems={problems} form={fieldId} names={INSTRUCTIONS_NAME} />
          <p className="m-0 text-[12.5px] text-dim" id={`${fieldId}-count`}>
            {problem ?? `${String(draft.trim().length)} of ${String(maxChars)} characters.`}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setDraft(null);
              }}
            >
              {CANCEL}
            </Button>
            <Button type="submit" disabled={busy || problem !== null}>
              {SAVE}
            </Button>
          </div>
        </form>
      )}
      {row.overridden && row.template_instructions ? (
        <details className="mt-3 rounded-md border border-line">
          <summary className="flex min-h-11 cursor-pointer items-center px-3 text-[13px] text-ink sm:min-h-9">{TEMPLATE_INSTRUCTIONS}</summary>
          <div className="border-t border-line px-3 py-2">
            <Lines text={row.template_instructions} />
          </div>
        </details>
      ) : null}
    </SectionCard>
  );
}

function PromptList({ body, onDone }: { readonly body: PromptsBody; readonly onDone: (sentence: string) => void }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  // The refusal, and the edit it refused when it was one, so its problems are drawn beside that
  // agent's text and no other.
  const [failure, setFailure] = useState<{ readonly failure: ApiFailure; readonly edited: string | null } | null>(null);

  function send(asked: Pending): void {
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
        setFailure({ failure: result.failure, edited: asked.kind === "edit" ? asked.row.agent_id : null });
        return;
      }
      setFailure(null);
      onDone(
        asked.kind === "edit"
          ? `${asked.row.display_name}'s instructions were replaced. It is given them from the next request.`
          : `${asked.row.display_name}'s instructions were given back to its template.`,
      );
    })();
  }

  const notes = [
    body.no_model_is_called_yet === false ? null : NO_MODEL_IS_CALLED_YET,
    body.every_change_is_in_the_audit_trail === false ? null : EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL,
  ].filter((one): one is string => one !== null);

  return (
    <>
      <SystemInstructions body={body} />
      {body.editing_switched_on ? null : <Note kind="not-yet">{EDITING_SWITCHED_OFF}</Note>}
      {failure === null ? null : (
        <FailureNotice failure={failure.failure} {...(failure.edited === null ? {} : { fields: [INSTRUCTIONS_NAME] })} />
      )}
      {body.agents.length === 0 ? (
        <EmptyState title={NO_AGENTS_TITLE} description={NO_AGENTS} />
      ) : (
        body.agents.map((row) => (
          <AgentCard
            key={row.agent_id}
            row={row}
            maxChars={body.max_chars}
            busy={busy}
            problems={failure !== null && failure.edited === row.agent_id ? failure.failure.problems : []}
            onAsk={(asked) => {
              setFailure(null);
              setPending(asked);
            }}
          />
        ))
      )}
      {notes.length === 0 ? null : (
        <div className="flex flex-col gap-1">
          {notes.map((one) => (
            <Note key={one}>{one}</Note>
          ))}
        </div>
      )}
      {body.agents.length === 0 ? null : (
        <Advanced>
          <FactList>
            {body.agents.map((row) => (
              <Fact key={row.agent_id} label={row.display_name}>
                <span className="font-mono text-[11.5px]">{row.agent_id}</span>
                {row.template_id ? <span className="block font-mono text-[11px] text-dim">Template {row.template_id}</span> : null}
                {row.set_by ? <span className="block font-mono text-[11px] text-dim">Set by {row.set_by}</span> : null}
              </Fact>
            ))}
          </FactList>
        </Advanced>
      )}
      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "" : pending.kind === "edit" ? editQuestion(pending.row) : giveBackQuestion(pending.row)}
        consequence={pending === null ? "" : pending.kind === "edit" ? editConsequence(pending.row) : giveBackConsequence(pending.row)}
        confirmLabel={pending?.kind === "give-back" ? GIVE_BACK : SAVE}
        cancelLabel={KEEP_IT}
        busy={busy}
        onConfirm={() => {
          if (pending !== null) {
            send(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </>
  );
}

export function PromptsPage() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const answer = useResource<unknown>(PROMPTS_API_PATH, version);
  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_PROMPTS} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readPrompts(answer.data);
    content =
      body === null ? (
        <Note>{UNREADABLE_ANSWER}</Note>
      ) : (
        <PromptList
          body={body}
          onDone={(sentence) => {
            setTold(sentence);
            setVersion((count) => count + 1);
          }}
        />
      );
  }
  return (
    <div data-slot="prompts-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: PROMPTS_LABEL }]} title={PROMPTS_LABEL} lede={PROMPTS_LEDE} />
      {told === null ? null : (
        <div role="status">
          <Note kind="works">{told}</Note>
        </div>
      )}
      {content}
    </div>
  );
}
