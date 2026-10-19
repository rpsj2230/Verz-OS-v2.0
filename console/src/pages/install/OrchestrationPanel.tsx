/**
 * Multi-agent plans on the Features page: the plans the gate has weighed and what it decided, and a
 * place to weigh one by pasting it.
 *
 * **Nothing here decides who may.** The route asks for `admin:agent_lifecycle` over everything and
 * refuses everybody else before it reads anything, and a refusal is shown as the API wrote it. A
 * write is followed by a fresh read, so the page shows what the database holds.
 *
 * Task ids: M18.2.1, M18.2.2, M18.2.3, M18.2.4, M18.1.3, M18.4.1, M18.4.2, M18.4.3
 */

import { useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Chip, EmptyList, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";
import { moneyWords } from "../spendQuery";
import {
  NO_DECISIONS,
  NO_DECISIONS_TITLE,
  NOT_JSON,
  NOT_WEIGHED,
  NOTHING_STARTS,
  ORCHESTRATION_TITLE,
  PLAN_LABEL,
  READING_DECISIONS,
  readDecisions,
  readPlan,
  readRehearsal,
  REHEARSALS_API_PATH,
  summary,
  SWITCHED_OFF,
  UNREADABLE_DECISIONS,
  verdictWords,
  WEIGH,
  type DecisionsBody,
  type RehearsalBody,
} from "../orchestrationQuery";

function Answer({ one }: { readonly one: RehearsalBody }) {
  const merged = one.merged;
  return (
    <SectionCard title={verdictWords(one.gate.verdict)} headingLevel="h3" action={<Chip>{one.gate.verdict}</Chip>}>
      <p className="m-0 text-[13px] text-body">{summary(one.gate)}</p>
      {merged === null || merged === undefined ? null : (
        <>
          <p className="m-0 mt-2 text-[12.5px] text-dim">
            {merged.complete ? "Every subtask returned what it promised." : merged.notice}
          </p>
          <ul className="m-0 mt-1 list-none p-0 text-[12.5px] text-dim">
            {merged.reports.map((row) => (
              <li key={row.subtask_id}>
                {row.subtask_id}: {moneyWords(row.minor, merged.currency)}, {row.seconds} seconds
              </li>
            ))}
          </ul>
          <p className="m-0 mt-1 text-[12.5px] text-body">Total cost: {moneyWords(merged.total_minor, merged.currency)}.</p>
        </>
      )}
    </SectionCard>
  );
}

/**
 * The last answer is held by the panel and not here: weighing re-reads the list, which draws the
 * loading sentence in the list's place, and an answer held by what that replaces would be lost the
 * moment it arrived.
 */
function Weigher({
  last,
  onWeighed,
}: {
  readonly last: RehearsalBody | null;
  readonly onWeighed: (answer: RehearsalBody | null) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  function weigh(): void {
    const plan = readPlan(text);
    if (plan === null) {
      setProblem(NOT_JSON);
      return;
    }
    setProblem(null);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(REHEARSALS_API_PATH, { method: "POST", body: plan });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onWeighed(readRehearsal(result.data));
    })();
  }

  return (
    <SectionCard title={WEIGH} headingLevel="h3">
      <label className="m-0 block text-[13px] text-body" htmlFor="plan-to-weigh">
        {PLAN_LABEL}
      </label>
      <Textarea
        id="plan-to-weigh"
        value={text}
        rows={8}
        className="mt-1 font-mono text-[12px]"
        onChange={(event) => {
          setText(event.target.value);
        }}
      />
      {problem === null ? null : <Note>{problem}</Note>}
      {failure === null ? null : <FailureState failure={failure} title={NOT_WEIGHED} />}
      <div className="mt-2">
        <Button size="sm" className="min-h-11 sm:min-h-8" disabled={busy || text.trim() === ""} onClick={weigh}>
          {WEIGH}
        </Button>
      </div>
      {last === null ? null : <Answer one={last} />}
    </SectionCard>
  );
}

function DecisionList({
  body,
  last,
  onWeighed,
}: {
  readonly body: DecisionsBody;
  readonly last: RehearsalBody | null;
  readonly onWeighed: (answer: RehearsalBody | null) => void;
}) {
  return (
    <>
      <Note>{NOTHING_STARTS}</Note>
      {body.rehearsal_is_on ? null : <Note>{SWITCHED_OFF}</Note>}
      {body.decisions.length === 0 ? (
        <EmptyList
          title={NO_DECISIONS_TITLE}
          description={NO_DECISIONS}
          adds="Weigh a plan with the form on this screen, and its verdict is kept."
          by={["super_admin"]}
        />
      ) : null}
      {body.decisions.map((row) => (
        <SectionCard
          key={row.run_id}
          title={verdictWords(row.verdict)}
          headingLevel="h3"
          action={<Chip>{row.verdict}</Chip>}
        >
          <p className="m-0 text-[13px] text-body">{summary(row)}</p>
        </SectionCard>
      ))}
      {body.rehearsal_is_on ? <Weigher last={last} onWeighed={onWeighed} /> : null}
      <Note>{body.weights_note}</Note>
    </>
  );
}

export function OrchestrationPanel() {
  const [version, setVersion] = useState(0);
  const [last, setLast] = useState<RehearsalBody | null>(null);
  const answer = useResource<unknown>(REHEARSALS_API_PATH, version);

  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_DECISIONS} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readDecisions(answer.data);
    content =
      body === null ? (
        <Note>{UNREADABLE_DECISIONS}</Note>
      ) : (
        <DecisionList
          body={body}
          last={last}
          onWeighed={(weighed) => {
            setLast(weighed);
            setVersion((count) => count + 1);
          }}
        />
      );
  }
  return (
    <section data-slot="orchestration-panel" aria-label={ORCHESTRATION_TITLE} className="flex min-w-0 flex-col gap-3">
      <h2 className="m-0 text-[15px] font-semibold">{ORCHESTRATION_TITLE}</h2>
      {content}
    </section>
  );
}
