/**
 * Quick answers on the shared page kit: the fast-lane rules a reader may see, each with the words
 * it answers and the column it answers with, a Retire on each, and a form that tries a rule against
 * a real question before adding it.
 *
 * **Nothing here decides who may do what.** `brain.rule_routes` lists the rules at the places the
 * reader's grant admits, refuses a rule another department wrote in the words a missing rule gets,
 * and refuses a place the administrator may not write; the page draws each refusal as the API sent
 * it. The department box is filled with the department the API says the reader works in, and
 * nothing in the browser narrows what may be typed into it, because the API is the one answer.
 *
 * **One card per rule rather than a table.** A rule is a sentence of question words and two column
 * names, which wraps; a row of columns holding it is wider than a phone or cuts off the words, and
 * the words are what an administrator recognises. The Possible duplicates card is shaped the same
 * way for the same reason.
 *
 * **Try it before Add, and trying saves nothing.** The test runs the lane at the administrator's own
 * reach, so it says what their own question would be answered with, which is the check a person
 * makes before trusting a rule with everybody's. Add is not disabled until a try succeeds, because a
 * rule over a table the administrator may not read themselves is legitimate and tries as answering
 * nothing.
 *
 * **After an addition or a retirement the list is read again**, so the page shows what the database
 * holds, which is what the next question is answered from. A refused addition is said and the list
 * is not read again, so what was typed is still there to correct.
 *
 * **What was put in Advanced rather than on the card**: the rule's id as stored, which carries its
 * department as a prefix, and where its table lives.
 *
 * Task ids: M6.5.1
 */

import { useId, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
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
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import {
  ADD,
  ADD_HEADING,
  ADD_LEDE,
  ADDED_BY,
  ANSWER_HINT,
  ANSWER_LABEL,
  ANSWERS_WITH,
  ASKED_BY,
  DEPARTMENT_HINT,
  DEPARTMENT_HINT_INSTALL,
  DEPARTMENT_LABEL,
  emptyDraft,
  ENTITY_HINT,
  ENTITY_LABEL,
  FILL_EVERY_BOX,
  FROM_TABLE,
  KEEP,
  LIVE_HEADING,
  MATCH_HINT,
  MATCH_LABEL,
  NAME_HINT,
  NAME_LABEL,
  NEEDS_A_QUESTION,
  NO_RULES,
  NO_RULES_TITLE,
  NOT_ADDED,
  NOT_RETIRED,
  NOT_TRIED,
  placeOf,
  QUESTION_HINT,
  QUESTION_LABEL,
  READING_RULES,
  readRules,
  readTrial,
  readWritten,
  retireApiPath,
  RETIRE,
  RETIRE_CONSEQUENCE,
  RETIRE_QUESTION,
  ruleBody,
  RULES_API_PATH,
  RULES_LABEL,
  RULES_LEDE,
  SLOT_HINT,
  SLOT_LABEL,
  SOURCE_HINT,
  SOURCE_LABEL,
  TEMPLATE_HINT,
  TEMPLATE_LABEL,
  trialBody,
  TRY,
  TRY_API_PATH,
  UNREADABLE_ANSWER,
  type RuleDraft,
  type RulesBody,
  type RuleShown,
  type RuleTrial,
} from "../rulesQuery";
import { when } from "../sessionsQuery";

/** What the page was told after a write: done, or not, in the API's sentence. */
interface Told {
  readonly sentence: string;
  readonly done: boolean;
}

function RuleCard({ rule, busy, onRetire }: { readonly rule: RuleShown; readonly busy: boolean; readonly onRetire: (rule: RuleShown) => void }) {
  return (
    <SectionCard
      title={rule.template}
      headingLevel="h3"
      lede={`${ASKED_BY} ${placeOf(rule)}.`}
      footer={
        <p data-slot="rule-added" className="m-0 text-[12px] text-dim">
          {ADDED_BY} {rule.created_by}, {when(rule.created_at)}.
        </p>
      }
    >
      <p className="m-0 text-[13px] text-body [overflow-wrap:anywhere]">
        {ANSWERS_WITH} <span className="font-medium text-ink">{rule.answer_field}</span> {FROM_TABLE}{" "}
        <span className="font-medium text-ink">{rule.entity}</span>.
      </p>
      <div className="mt-3">
        <Button
          size="sm"
          variant="outline"
          className="min-h-11 sm:min-h-8"
          disabled={busy}
          aria-label={`${RETIRE}: ${rule.template}`}
          onClick={() => {
            onRetire(rule);
          }}
        >
          {RETIRE}
        </Button>
      </div>
    </SectionCard>
  );
}

function Field({
  label,
  hint,
  value,
  name,
  onChange,
}: {
  readonly label: string;
  readonly hint: string;
  readonly value: string;
  readonly name: string;
  readonly onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <p id={`${id}-hint`} className="m-0 text-[12px] leading-snug text-dim">
        {hint}
      </p>
      <Input
        id={id}
        name={name}
        value={value}
        aria-describedby={`${id}-hint`}
        className="min-h-11 sm:min-h-9"
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
    </div>
  );
}

function AddForm({ body, onWritten }: { readonly body: RulesBody; readonly onWritten: (told: Told) => void }) {
  const [draft, setDraft] = useState<RuleDraft>(() => emptyDraft(body.own_department));
  const [problem, setProblem] = useState<string | null>(null);
  const [trial, setTrial] = useState<RuleTrial | null>(null);
  const [failure, setFailure] = useState<{ readonly failure: ApiFailure; readonly title: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function set(key: keyof RuleDraft): (value: string) => void {
    return (value) => {
      setDraft((was) => ({ ...was, [key]: value }));
      setProblem(null);
      setTrial(null);
    };
  }

  function tryIt(): void {
    const sent = trialBody(draft);
    if (sent === null) {
      setProblem(ruleBody(draft) === null ? FILL_EVERY_BOX : NEEDS_A_QUESTION);
      return;
    }
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(TRY_API_PATH, { method: "POST", body: sent });
      setBusy(false);
      if (!result.ok) {
        setFailure({ failure: result.failure, title: NOT_TRIED });
        return;
      }
      setTrial(readTrial(result.data));
    })();
  }

  function add(): void {
    const sent = ruleBody(draft);
    if (sent === null) {
      setProblem(FILL_EVERY_BOX);
      return;
    }
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(RULES_API_PATH, { method: "POST", body: sent });
      setBusy(false);
      if (!result.ok) {
        setFailure({ failure: result.failure, title: NOT_ADDED });
        return;
      }
      const written = readWritten(result.data);
      if (written === null) {
        return;
      }
      if (written.done) {
        setDraft(emptyDraft(body.own_department));
        setTrial(null);
      }
      onWritten({ sentence: written.told, done: written.done });
    })();
  }

  return (
    <SectionCard title={ADD_HEADING} lede={ADD_LEDE}>
      <form
        data-slot="rule-form"
        className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault();
          add();
        }}
      >
        <Field label={NAME_LABEL} hint={NAME_HINT} name="name" value={draft.name} onChange={set("name")} />
        <Field
          label={DEPARTMENT_LABEL}
          hint={body.may_write_install ? DEPARTMENT_HINT_INSTALL : DEPARTMENT_HINT}
          name="department"
          value={draft.department}
          onChange={set("department")}
        />
        <div className="sm:col-span-2">
          <Field label={TEMPLATE_LABEL} hint={TEMPLATE_HINT} name="template" value={draft.template} onChange={set("template")} />
        </div>
        <Field label={SLOT_LABEL} hint={SLOT_HINT} name="slot" value={draft.slot} onChange={set("slot")} />
        <Field label={ENTITY_LABEL} hint={ENTITY_HINT} name="entity" value={draft.entity} onChange={set("entity")} />
        <Field label={MATCH_LABEL} hint={MATCH_HINT} name="match_field" value={draft.matchField} onChange={set("matchField")} />
        <Field label={ANSWER_LABEL} hint={ANSWER_HINT} name="answer_field" value={draft.answerField} onChange={set("answerField")} />
        <Field label={SOURCE_LABEL} hint={SOURCE_HINT} name="source" value={draft.source} onChange={set("source")} />
        <div className="sm:col-span-2">
          <Field label={QUESTION_LABEL} hint={QUESTION_HINT} name="question" value={draft.question} onChange={set("question")} />
        </div>
        {problem === null ? null : (
          <p data-slot="rule-problem" className="m-0 text-[12px] text-crit sm:col-span-2">
            {problem}
          </p>
        )}
        {trial === null ? null : (
          <div data-slot="rule-trial" role="status" className="sm:col-span-2">
            <Note kind={trial.answer === null ? "info" : "done"}>
              {trial.told}
              {trial.answer === null ? null : (
                <span className="mt-1 block font-medium text-ink [overflow-wrap:anywhere]">{trial.answer}</span>
              )}
            </Note>
          </div>
        )}
        {failure === null ? null : (
          <div className="sm:col-span-2">
            <FailureState failure={failure.failure} title={failure.title} />
          </div>
        )}
        <div className="flex flex-wrap gap-2 sm:col-span-2">
          <Button type="button" variant="outline" className="min-h-11 sm:min-h-9" disabled={busy} onClick={tryIt}>
            {TRY}
          </Button>
          <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
            {ADD}
          </Button>
        </div>
      </form>
    </SectionCard>
  );
}

function RuleList({ body, onWritten }: { readonly body: RulesBody; readonly onWritten: (told: Told) => void }) {
  const [retiring, setRetiring] = useState<RuleShown | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  function retire(rule: RuleShown): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(retireApiPath(rule.rule_id), { method: "POST" });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const written = readWritten(result.data);
      setRetiring(null);
      if (written !== null) {
        onWritten({ sentence: written.told, done: written.done });
      }
    })();
  }

  return (
    <section data-slot="rules-live" aria-label={LIVE_HEADING} className="flex min-w-0 flex-col gap-3">
      <h2 className="m-0 text-sm font-semibold text-ink">{LIVE_HEADING}</h2>
      {body.rules.length === 0 ? (
        <EmptyState title={NO_RULES_TITLE} description={NO_RULES} />
      ) : (
        body.rules.map((rule) => (
          <RuleCard
            key={rule.rule_id}
            rule={rule}
            busy={busy}
            onRetire={(chosen) => {
              setFailure(null);
              setRetiring(chosen);
            }}
          />
        ))
      )}
      {body.rules.length === 0 ? null : (
        <Advanced>
          <FactList>
            {body.rules.map((rule) => (
              <Fact key={rule.rule_id} label={rule.template}>
                <span className="font-mono text-[11.5px]">{rule.rule_id}</span>
                <span className="block font-mono text-[11px] text-dim">
                  {rule.source}/{rule.entity}: {rule.match_field} to {rule.answer_field}
                </span>
              </Fact>
            ))}
          </FactList>
        </Advanced>
      )}
      <ConfirmDialog
        open={retiring !== null}
        question={RETIRE_QUESTION}
        consequence={RETIRE_CONSEQUENCE}
        details={
          retiring === null ? undefined : (
            <div className="flex min-w-0 flex-col gap-1.5">
              <p className="m-0 text-[13px] font-medium text-ink [overflow-wrap:anywhere]">{retiring.template}</p>
              {failure === null ? null : <FailureState failure={failure} title={NOT_RETIRED} />}
            </div>
          )
        }
        confirmLabel={RETIRE}
        cancelLabel={KEEP}
        danger
        busy={busy}
        onConfirm={() => {
          if (retiring !== null) {
            retire(retiring);
          }
        }}
        onCancel={() => {
          setRetiring(null);
        }}
      />
    </section>
  );
}

export function RulesPage() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<Told | null>(null);
  const answer = useResource<unknown>(RULES_API_PATH, version);

  // Read again only after something changed, so a refused addition keeps what was typed.
  function written(next: Told): void {
    setTold(next);
    if (next.done) {
      setVersion((count) => count + 1);
    }
  }

  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_RULES} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readRules(answer.data);
    content =
      body === null ? (
        <Note>{UNREADABLE_ANSWER}</Note>
      ) : (
        <>
          <RuleList body={body} onWritten={written} />
          <AddForm body={body} onWritten={written} />
        </>
      );
  }
  return (
    <div data-slot="rules-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: RULES_LABEL }]} title={RULES_LABEL} lede={RULES_LEDE} />
      {told === null ? null : (
        <div role="status">
          <Note kind={told.done ? "done" : "info"}>{told.sentence}</Note>
        </div>
      )}
      {content}
    </div>
  );
}
