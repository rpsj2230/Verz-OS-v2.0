/**
 * The writes of Compliance: naming the person a sensitive topic is routed to, opening a breach
 * case, and recording each step of one (the assessment, the Commission notified, the individuals
 * notified, a decision not to notify them) and closing it.
 *
 * **Every write here is confirmed, and every one is a record that cannot be taken back.** Naming a
 * person replaces whoever was named; opening a case starts a statutory clock; an assessment, a
 * notification and an exception are each a claim the Commission may later ask about; closing ends
 * the case. Each form says what its fields take before it is sent and is judged in
 * `complianceQuery.ts` first, so a confirmation is only ever about a write whose shape the route will
 * accept.
 *
 * Task ids: M24.2.2, M24.2.4, M27.16.1
 */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, Drawer, FailureState } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Field, FormProblem, NativeSelect } from "../access/formParts";
import {
  assessBody,
  assessProblems,
  AWARENESS_BASES,
  AWARENESS_SOURCES,
  BREACHES_API_PATH,
  breachStepApiPath,
  EMPTY_ASSESS,
  EMPTY_EXCEPTION,
  EMPTY_OPEN,
  EXCEPTION_GROUNDS,
  exceptionBody,
  exceptionProblems,
  GROUND_LABELS,
  labelOf,
  nameBody,
  nameProblems,
  notifiedBody,
  notifiedProblems,
  openBody,
  openProblems,
  SOURCE_LABELS,
  topicApiPath,
  type AssessForm,
  type Breach,
  type ExceptionForm,
  type OpenForm,
  type Topic,
} from "../complianceQuery";
import { nameOf, whenWords } from "../review/parts";

export const OPEN_FORM_LABEL = "Open a breach case";
export const OPEN_LABEL = "Open the case";
export const DO_NOT_OPEN = "Do not open it";
export const REVIEW_CASE = "Review the case";
export const NAME_FORM_LABEL = "Name the person a topic is routed to";
export const NAME_LABEL = "Name this person";
export const KEEP_NAMED = "Keep it as it is";
export const ASSESS_LABEL = "Record the assessment";
export const COMMISSION_LABEL = "Record the Commission notified";
export const INDIVIDUALS_LABEL = "Record the individuals notified";
export const EXCEPTION_FORM_LABEL = "Record a decision not to notify the individuals";
export const EXCEPTION_LABEL = "Record the decision";
export const CLOSE_LABEL = "Close the case";
export const DO_NOT_RECORD = "Do not record it";
export const KEEP_OPEN = "Keep it open";
export const REVIEW_STEP = "Review";

export const OPENING =
  "The case is recorded with you as its recorder and now as the moment it was recorded, and every deadline runs from the earliest moment of awareness, not from now. A case is never removed.";

export const HINTS = Object.freeze({
  becameAwareAt: "The date and time there was first reason to believe a breach had happened, on this device's clock. Not in the future.",
  basis: "Whether that moment was read off a record, or is an estimate.",
  earliestPossibleAt: "For an estimate: the earliest the moment could have been. The clock runs from here.",
  source: "Where the reason to believe came from.",
  evidenceReference: "Where the evidence is, such as the alert or ticket number: up to 128 letters, digits and . _ @ -, no spaces, no description.",
  harm: "Your judgement, recorded as yours.",
  rationaleReference: "Where the reasoning is written, as a reference with no spaces: up to 128 letters, digits and . _ @ -.",
  affectedCount: "A whole number, or blank while it is not yet known. Blank is never zero.",
  notifiedAt: "The date and time the notification was made, on this device's clock. Not in the future.",
  ground: "The ground the decision is filed under.",
  principalId: "The person's reference as their page in People shows it under Advanced, with no spaces.",
});

function stamp(payload: unknown, key: string): string {
  const found = typeof payload === "object" && payload !== null ? (payload as Record<string, unknown>)[key] : undefined;
  return typeof found === "string" ? found : "";
}

/** One write in flight and its refusal. `path` and `method` are the write's; the page confirms first. */
export function useComplianceWrite(onDone: (told: string) => void) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const send = useCallback(
    (path: string, method: "POST" | "PUT", body: unknown, told: (payload: unknown) => string, after: () => void) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(path, { method, body });
        setBusy(false);
        after();
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onDone(told(result.data));
      })();
    },
    [onDone],
  );
  return { busy, failure, setFailure, send };
}

function Problems({ problems }: { readonly problems: readonly string[] }) {
  return problems.length === 0 ? null : (
    <div className="flex flex-col gap-1">
      {problems.map((one) => (
        <FormProblem key={one}>{one}</FormProblem>
      ))}
    </div>
  );
}

function Frame({
  title,
  description,
  formId,
  busy,
  cancel,
  submit,
  onClose,
  children,
}: {
  readonly title: string;
  readonly description: string;
  readonly formId: string;
  readonly busy: boolean;
  readonly cancel: string;
  readonly submit: string;
  readonly onClose: () => void;
  readonly children: ReactNode;
}) {
  return (
    <Drawer
      open
      onOpenChange={(next) => {
        if (!next && !busy) {
          onClose();
        }
      }}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            {cancel}
          </Button>
          <Button type="submit" form={formId} disabled={busy}>
            {submit}
          </Button>
        </>
      }
    >
      {children}
    </Drawer>
  );
}

/** The drawer a breach case is opened from. */
export function OpenCaseDrawer({ onClose, onDone }: { readonly onClose: () => void; readonly onDone: (told: string) => void }) {
  const [form, setForm] = useState<OpenForm>(EMPTY_OPEN);
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const write = useComplianceWrite(onDone);
  const set = (name: keyof OpenForm) => (value: string) => {
    setForm({ ...form, [name]: value });
  };
  const body = openBody(form);
  return (
    <Frame title={OPEN_FORM_LABEL} description="Starts the case's statutory clock from the earliest moment of awareness." formId="open-case" busy={write.busy} cancel={DO_NOT_OPEN} submit={REVIEW_CASE} onClose={onClose}>
      <form
        id="open-case"
        aria-label={OPEN_FORM_LABEL}
        className="flex min-w-0 flex-col gap-4"
        noValidate
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const found = openProblems(form, new Date());
          setProblems(found);
          if (found.length === 0) {
            write.setFailure(null);
            setConfirming(true);
          }
        }}
      >
        {write.failure === null ? null : <FailureState failure={write.failure} />}
        <Field label="When there was first reason to believe it" hint={HINTS.becameAwareAt}>
          {({ id, describedBy }) => <Input id={id} type="datetime-local" name="became_aware_at" aria-describedby={describedBy || undefined} value={form.becameAwareAt} onChange={(event) => set("becameAwareAt")(event.target.value)} />}
        </Field>
        <Field label="How that moment is known" hint={HINTS.basis}>
          {(ids) => (
            <NativeSelect {...ids} value={form.basis} onChange={set("basis")}>
              <option value="">Choose</option>
              {AWARENESS_BASES.map((one) => (
                <option key={one} value={one}>
                  {one === "observed" ? "Observed from a record" : "An estimate"}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        {form.basis === "estimated" ? (
          <Field label="The earliest it could have been" hint={HINTS.earliestPossibleAt}>
            {({ id, describedBy }) => <Input id={id} type="datetime-local" name="earliest_possible_at" aria-describedby={describedBy || undefined} value={form.earliestPossibleAt} onChange={(event) => set("earliestPossibleAt")(event.target.value)} />}
          </Field>
        ) : null}
        <Field label="Where it came from" hint={HINTS.source}>
          {(ids) => (
            <NativeSelect {...ids} value={form.source} onChange={set("source")}>
              <option value="">Choose</option>
              {AWARENESS_SOURCES.map((one) => (
                <option key={one} value={one}>
                  {labelOf(SOURCE_LABELS, one)}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="Where the evidence is" hint={HINTS.evidenceReference}>
          {({ id, describedBy }) => <Input id={id} name="evidence_reference" autoComplete="off" aria-describedby={describedBy || undefined} value={form.evidenceReference} onChange={(event) => set("evidenceReference")(event.target.value)} />}
        </Field>
        <Problems problems={problems} />
      </form>
      <ConfirmDialog
        open={confirming}
        question={`Open a breach case from awareness at ${whenWords(body.became_aware_at)}, evidence ${body.evidence_reference}?`}
        consequence={OPENING}
        confirmLabel={OPEN_LABEL}
        cancelLabel={DO_NOT_OPEN}
        busy={write.busy}
        onConfirm={() => {
          write.send(BREACHES_API_PATH, "POST", body, () => `A breach case was opened for evidence ${body.evidence_reference}.`, () => {
            setConfirming(false);
          });
        }}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </Frame>
  );
}

/** Naming the person one topic is routed to. */
export function NameDrawer({ topic, onClose, onDone, people }: { readonly topic: Topic; readonly onClose: () => void; readonly onDone: (told: string) => void; readonly people: Readonly<Record<string, string>> }) {
  const [principalId, setPrincipalId] = useState("");
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const write = useComplianceWrite(onDone);
  const current = topic.named === null ? null : nameOf(people, topic.named.principal_id);
  return (
    <Frame title={`${NAME_FORM_LABEL}: ${topic.label}`} description="Notes that somebody asked about this topic go to this person, and to nobody else." formId="name-topic" busy={write.busy} cancel={KEEP_NAMED} submit={NAME_LABEL} onClose={onClose}>
      <form
        id="name-topic"
        aria-label={NAME_FORM_LABEL}
        className="flex min-w-0 flex-col gap-4"
        noValidate
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const found = nameProblems({ topic: topic.topic, principalId }, [topic.topic]);
          setProblems(found);
          if (found.length === 0) {
            write.setFailure(null);
            setConfirming(true);
          }
        }}
      >
        {write.failure === null ? null : <FailureState failure={write.failure} />}
        <Field label="Person, by reference" hint={HINTS.principalId}>
          {({ id, describedBy }) => <Input id={id} name="principal_id" autoComplete="off" aria-describedby={describedBy || undefined} value={principalId} onChange={(event) => setPrincipalId(event.target.value)} />}
        </Field>
        <Problems problems={problems} />
      </form>
      <ConfirmDialog
        open={confirming}
        question={`Route ${topic.label} questions to ${principalId.trim()}?`}
        consequence={`From now, a note that somebody asked about ${topic.label}, without what they wrote, goes to ${principalId.trim()}${current === null ? "." : `, in place of ${current}.`}`}
        confirmLabel={NAME_LABEL}
        cancelLabel={KEEP_NAMED}
        busy={write.busy}
        onConfirm={() => {
          write.send(topicApiPath(topic.topic), "PUT", nameBody({ topic: topic.topic, principalId }), (payload) => `Somebody was named for ${topic.label} at ${whenWords(stamp(payload, "named_at"))}.`, () => {
            setConfirming(false);
          });
        }}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </Frame>
  );
}

export type Step = "assessment" | "commission" | "individuals" | "exception";

const STEP_LABELS: Readonly<Record<Step, string>> = Object.freeze({
  assessment: ASSESS_LABEL,
  commission: COMMISSION_LABEL,
  individuals: INDIVIDUALS_LABEL,
  exception: EXCEPTION_FORM_LABEL,
});

/** Recording one step of an open case. */
export function StepDrawer({ one, step, onClose, onDone }: { readonly one: Breach; readonly step: Step; readonly onClose: () => void; readonly onDone: (told: string) => void }) {
  const [assess, setAssess] = useState<AssessForm>(EMPTY_ASSESS);
  const [at, setAt] = useState("");
  const [exception, setException] = useState<ExceptionForm>(EMPTY_EXCEPTION);
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const write = useComplianceWrite(onDone);
  const name = one.evidence_reference;
  const body = step === "assessment" ? assessBody(assess) : step === "exception" ? exceptionBody(exception) : notifiedBody(at);
  const judged = () =>
    step === "assessment" ? assessProblems(assess) : step === "exception" ? exceptionProblems(exception) : notifiedProblems(at, new Date());
  const question =
    step === "assessment"
      ? `Record that breach case ${name} is ${assess.harm === "yes" ? "" : "not "}likely to result in significant harm?`
      : step === "exception"
        ? `Record a decision not to notify the individuals affected by breach case ${name}?`
        : `Record that ${step === "commission" ? "the Commission was" : "the individuals affected were"} notified of breach case ${name} at ${whenWords(notifiedBody(at).at ?? "")}?`;
  const consequence =
    step === "assessment"
      ? "The judgement is recorded as yours, with where its reasoning is. The deadlines to notify follow from it."
      : step === "exception"
        ? `It is filed under "${labelOf(GROUND_LABELS, exception.ground)}" as your decision, with where its reasoning is.`
        : "The case records the notification at that moment, and the deadline shows whether it was in time.";
  return (
    <Frame title={STEP_LABELS[step]} description={`For breach case ${name}. Recorded once, as yours.`} formId="case-step" busy={write.busy} cancel={DO_NOT_RECORD} submit={REVIEW_STEP} onClose={onClose}>
      <form
        id="case-step"
        aria-label={STEP_LABELS[step]}
        className="flex min-w-0 flex-col gap-4"
        noValidate
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const found = judged();
          setProblems(found);
          if (found.length === 0) {
            write.setFailure(null);
            setConfirming(true);
          }
        }}
      >
        {write.failure === null ? null : <FailureState failure={write.failure} />}
        {step === "assessment" ? (
          <>
            <Field label="Likely to result in significant harm" hint={HINTS.harm}>
              {(ids) => (
                <NativeSelect {...ids} value={assess.harm} onChange={(value) => setAssess({ ...assess, harm: value })}>
                  <option value="">Choose</option>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </NativeSelect>
              )}
            </Field>
            <Field label="Where the reasoning is written" hint={HINTS.rationaleReference}>
              {({ id, describedBy }) => <Input id={id} name="rationale_reference" autoComplete="off" aria-describedby={describedBy || undefined} value={assess.rationaleReference} onChange={(event) => setAssess({ ...assess, rationaleReference: event.target.value })} />}
            </Field>
            <Field label="How many people are affected, if known" hint={HINTS.affectedCount}>
              {({ id, describedBy }) => <Input id={id} name="affected_count" inputMode="numeric" aria-describedby={describedBy || undefined} value={assess.affectedCount} onChange={(event) => setAssess({ ...assess, affectedCount: event.target.value })} />}
            </Field>
          </>
        ) : step === "exception" ? (
          <>
            <Field label="Ground" hint={HINTS.ground}>
              {(ids) => (
                <NativeSelect {...ids} value={exception.ground} onChange={(value) => setException({ ...exception, ground: value })}>
                  <option value="">Choose a ground</option>
                  {EXCEPTION_GROUNDS.map((ground) => (
                    <option key={ground} value={ground}>
                      {labelOf(GROUND_LABELS, ground)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field label="Where the decision is reasoned" hint={HINTS.rationaleReference}>
              {({ id, describedBy }) => <Input id={id} name="rationale_reference" autoComplete="off" aria-describedby={describedBy || undefined} value={exception.rationaleReference} onChange={(event) => setException({ ...exception, rationaleReference: event.target.value })} />}
            </Field>
          </>
        ) : (
          <Field label={step === "commission" ? "When the Commission was notified" : "When the individuals were notified"} hint={HINTS.notifiedAt}>
            {({ id, describedBy }) => <Input id={id} type="datetime-local" name="at" aria-describedby={describedBy || undefined} value={at} onChange={(event) => setAt(event.target.value)} />}
          </Field>
        )}
        <Problems problems={problems} />
      </form>
      <ConfirmDialog
        open={confirming}
        question={question}
        consequence={consequence}
        confirmLabel={step === "exception" ? EXCEPTION_LABEL : STEP_LABELS[step]}
        cancelLabel={DO_NOT_RECORD}
        busy={write.busy}
        onConfirm={() => {
          write.send(breachStepApiPath(one.case_id, step), "POST", body, () => `Breach case ${name}: ${STEP_LABELS[step].toLowerCase()}, done.`, () => {
            setConfirming(false);
          });
        }}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </Frame>
  );
}

/** Closing a case, which is only offered when the case says it is closable. */
export function useClose(one: Breach, onDone: (told: string) => void): { readonly ask: () => void; readonly drawn: ReactNode; readonly busy: boolean } {
  const [confirming, setConfirming] = useState(false);
  const write = useComplianceWrite(onDone);
  const drawn = (
    <>
      {write.failure === null ? null : <FailureState failure={write.failure} />}
      <ConfirmDialog
        open={confirming}
        question={`Close breach case ${one.evidence_reference}?`}
        consequence="A closed case takes no further steps and stays on record as it stands."
        confirmLabel={CLOSE_LABEL}
        cancelLabel={KEEP_OPEN}
        busy={write.busy}
        onConfirm={() => {
          write.send(breachStepApiPath(one.case_id, "close"), "POST", undefined, () => `Breach case ${one.evidence_reference} is closed.`, () => {
            setConfirming(false);
          });
        }}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </>
  );
  return {
    ask: () => {
      write.setFailure(null);
      setConfirming(true);
    },
    drawn,
    busy: write.busy,
  };
}
