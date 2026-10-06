/**
 * The Stop screen: everything stopped this reader may see, a stop that takes one press, and a resume
 * that needs a written reason (M27.2.8, M27.12.4).
 *
 * **Nothing here decides who may stop what.** The API answers 404 to a reader who may not open the
 * screen and to a stop or a resume outside their scope; the scopes offered are the ones the API says
 * something asks, so an axis nothing enforces is said in words rather than offered as working
 * (M27.15.16).
 *
 * **A stop is not confirmed and a resume is.** Stopping is the owner's one-press control, with no
 * reason required (`brain.ops.halt_store.A_STOP_NEEDS_NO_WORDS_AND_A_RESUME_DOES`); resuming ends a
 * stop somebody chose, so it asks for a reason first and then asks to be sure, and says whose stop
 * it lifts.
 *
 * **A store that cannot be read is said, not drawn as an empty list**, because in that moment every
 * request is being refused.
 *
 * Task ids: M27.2.8, M27.12.4, M27.15.10, M27.15.15, M27.15.16
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, EmptyState, FailureState, LoadingState, Note, PageHeader, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Field, FormProblem, NativeSelect, whenWords } from "../access/formParts";
import {
  CANNOT_TELL,
  HALTS_API_PATH,
  haltTitle,
  KEEP_IT_STOPPED,
  NOT_ASKED_YET_LEAD,
  NOT_RESUMED,
  NOT_STOPPED,
  NOTHING_STOPPED,
  NOTHING_STOPPED_TITLE,
  offeredScopes,
  readHalts,
  readResumed,
  READING_HALTS,
  REASON_HINT,
  REASON_LABEL,
  RESUME_API_PATH,
  RESUME_LABEL,
  RESUME_REASON_HINT,
  RESUME_REASON_LABEL,
  resumeBody,
  resumeConsequence,
  resumeProblem,
  resumeQuestion,
  SCOPE_LABEL,
  SCOPE_WORDS,
  STOP_FORM_LABEL,
  STOP_HEADING,
  STOP_LABEL,
  STOP_LEDE,
  stopBody,
  stopProblem,
  STOPPING,
  TARGET_HINT,
  TARGET_LABEL,
  UNREADABLE_ANSWER,
  type HaltRow,
  type HaltsBody,
  type HaltScope,
} from "../stopQuery";

function ResumeCard({ row, onResumed }: { readonly row: HaltRow; readonly onResumed: (said: string) => void }) {
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = resumeProblem(reason);
    setProblem(found);
    if (found === null) {
      setFailure(null);
      setConfirming(true);
    }
  };

  function resume(): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(RESUME_API_PATH, { method: "POST", body: resumeBody(row, reason) });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setConfirming(false);
      const resumed = readResumed(result.data);
      onResumed(resumed === null ? `${haltTitle(row)} was resumed.` : resumed.said);
    })();
  }

  return (
    <SectionCard
      title={haltTitle(row)}
      footer={
        <p className="m-0 text-[12px] text-dim">
          Stopped by {row.declared_by} {whenWords(row.at)}. {row.reason}
        </p>
      }
    >
      <form aria-label={`${RESUME_LABEL}: ${haltTitle(row)}`} className="flex min-w-0 flex-col gap-3" onSubmit={onSubmit} noValidate>
        <Field label={RESUME_REASON_LABEL} hint={RESUME_REASON_HINT} problem={problem}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid || undefined}
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
              }}
            />
          )}
        </Field>
        <div>
          <Button type="submit" variant="outline" className="min-h-11 sm:min-h-9" disabled={busy}>
            {RESUME_LABEL}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={confirming}
        question={resumeQuestion(row)}
        consequence={resumeConsequence(row)}
        details={failure === null ? undefined : <FailureState failure={failure} title={NOT_RESUMED} />}
        confirmLabel={RESUME_LABEL}
        cancelLabel={KEEP_IT_STOPPED}
        danger
        busy={busy}
        onConfirm={resume}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </SectionCard>
  );
}

function StopForm({ body, onStopped }: { readonly body: HaltsBody; readonly onStopped: (said: string) => void }) {
  const scopes = offeredScopes(body);
  // A named thing first: the one-press stop of everything is the header's control, and a form sent
  // with nothing filled in says what to fill in rather than stopping the install.
  const [scope, setScope] = useState<HaltScope>(scopes.find((one) => one !== "everything") ?? scopes[0] ?? "department");
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  if (scopes.length === 0) {
    return null;
  }
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = stopProblem(scope, target);
    setProblem(found);
    if (found !== null) {
      return;
    }
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(HALTS_API_PATH, { method: "POST", body: stopBody(scope, target, reason) });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setTarget("");
      setReason("");
      onStopped(`${haltTitle({ scope, target: target.trim() })} is stopped.`);
    })();
  };

  return (
    <SectionCard title={STOP_FORM_LABEL}>
      <form aria-label={STOP_FORM_LABEL} className="flex min-w-0 flex-col gap-3" onSubmit={onSubmit} noValidate>
        {failure === null ? null : <FailureState failure={failure} title={NOT_STOPPED} />}
        <Field label={SCOPE_LABEL}>
          {({ id, describedBy, invalid }) => (
            <NativeSelect
              id={id}
              describedBy={describedBy}
              invalid={invalid}
              value={scope}
              onChange={(value) => {
                setScope(value as HaltScope);
                setProblem(null);
              }}
            >
              {scopes.map((one) => (
                <option key={one} value={one}>
                  {SCOPE_WORDS[one]}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        {scope === "everything" ? null : (
          <Field label={TARGET_LABEL} hint={TARGET_HINT} problem={problem}>
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                maxLength={128}
                aria-describedby={describedBy}
                aria-invalid={invalid || undefined}
                value={target}
                onChange={(event) => {
                  setTarget(event.target.value);
                }}
              />
            )}
          </Field>
        )}
        <Field label={REASON_LABEL} hint={REASON_HINT}>
          {({ id, describedBy }) => (
            <Input
              id={id}
              maxLength={2000}
              aria-describedby={describedBy}
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
              }}
            />
          )}
        </Field>
        {problem !== null && scope === "everything" ? <FormProblem>{problem}</FormProblem> : null}
        <div>
          <Button type="submit" variant="destructive" className="min-h-11 sm:min-h-9" disabled={busy}>
            {STOP_LABEL}
          </Button>
        </div>
        {busy ? (
          <p role="status" className="m-0 text-[12.5px] text-dim">
            {STOPPING}
          </p>
        ) : null}
      </form>
    </SectionCard>
  );
}

function Stopped({ body, onChanged }: { readonly body: HaltsBody; readonly onChanged: (said: string) => void }) {
  return (
    <>
      {body.known ? null : <Note>{CANNOT_TELL}</Note>}
      {body.known && body.halts.length === 0 ? <EmptyState title={NOTHING_STOPPED_TITLE} description={NOTHING_STOPPED} /> : null}
      {body.halts.map((row) => (
        <ResumeCard key={`${row.scope}:${row.target}`} row={row} onResumed={onChanged} />
      ))}
      {body.gaps.map((one) => (
        <Note key={one}>
          {one}
        </Note>
      ))}
      <StopForm body={body} onStopped={onChanged} />
      {body.not_asked_yet.length === 0 ? null : (
        <Note>
          {NOT_ASKED_YET_LEAD} {body.not_asked_yet.map((one) => SCOPE_WORDS[one].toLowerCase()).join(", ")}.
        </Note>
      )}
    </>
  );
}

export function StopPage() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const answer = useResource<unknown>(HALTS_API_PATH, version);

  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_HALTS} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readHalts(answer.data);
    content =
      body === null ? (
        <Note>{UNREADABLE_ANSWER}</Note>
      ) : (
        <Stopped
          body={body}
          onChanged={(said) => {
            setTold(said);
            setVersion((count) => count + 1);
          }}
        />
      );
  }
  return (
    <div data-slot="stop-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: STOP_HEADING }]} title={STOP_HEADING} lede={STOP_LEDE} />
      {told === null ? null : (
        <div role="status">
          <Note kind="done">{told}</Note>
        </div>
      )}
      {content}
    </div>
  );
}
