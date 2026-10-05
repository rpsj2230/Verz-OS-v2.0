/**
 * Reading a run's trace, drawn (M32.5.2.3, M20.2.1): a trace id and a reason in, the run's graph out.
 *
 * **The trace graph was a component no page rendered.** `TraceGraph` drew a completed run, the
 * read route served one under the payload role, and nothing called the route for the component
 * to draw. This page is that call. It lives under the Audit log because reading a trace is an
 * incident's step, and the reason asked for is recorded against the reader before the route
 * answers.
 *
 * **One refusal, whatever the reason.** A reader whose sign-in does not carry the payload role,
 * and a trace id that names nothing, are answered the same by the route, and this page draws that
 * answer as it was sent rather than guessing which it was.
 *
 * **A read is sent only once the form holds what the route takes** (`traceQuery.traceProblems`),
 * and it is a write of one row, who read it and why, so it is listed with the forms that write.
 *
 * Task ids: M32.5.2.3, M20.2.1
 */

import { useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { PageHeader, SectionCard } from "../../components/kit";
import { TraceGraph } from "../../components/TraceGraph";
import { readCompletedRun, UnreadableGraph, type CompletedRun } from "../../components/graph";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Field } from "../access/formParts";
import { AUDIT_PATH } from "../auditQuery";
import {
  READ_REASON_CHARS,
  TRACE_HINTS,
  TRACE_ID_CHARS,
  TRACE_PROBLEMS,
  traceGraphPayload,
  traceProblems,
  traceReadBody,
  traceReadPath,
} from "../traceQuery";
import { AUDIT_HEADING } from "./AuditPage";

export const TRACE_HEADING = "Read a run's trace";
export const TRACE_LEDE =
  "Draws what happened on one finished run. Reading it is recorded against you with your reason, and only a sign-in holding the trace reader role is answered.";
export const TRACE_FORM_LABEL = "The trace to read";
export const READ_TRACE_LABEL = "Read the trace";
export const READING_TRACE = "Reading the trace.";
export const UNREADABLE_TRACE = "The answer was not a finished run's trace, so nothing is drawn.";

export function TracePage() {
  const { traceId: given } = useParams();
  const [traceId, setTraceId] = useState(given ?? "");
  const [reason, setReason] = useState("");
  const [problems, setProblems] = useState<readonly (keyof typeof TRACE_PROBLEMS)[]>([]);
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState<CompletedRun | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [unreadable, setUnreadable] = useState(false);
  const [read, setRead] = useState("");

  const onRead = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const missing = traceProblems(traceId, reason);
    setProblems(missing);
    if (missing.length > 0) {
      return;
    }
    const id = traceId.trim();
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(traceReadPath(id), { method: "POST", body: traceReadBody(reason) });
      setBusy(false);
      setRead(id);
      if (!result.ok) {
        setFailure(result.failure);
        setRun(null);
        setUnreadable(false);
        return;
      }
      setFailure(null);
      try {
        setRun(readCompletedRun(traceGraphPayload(result.data)));
        setUnreadable(false);
      } catch (error) {
        if (!(error instanceof UnreadableGraph)) {
          throw error;
        }
        setRun(null);
        setUnreadable(true);
      }
    })();
  };
  const problem = (name: keyof typeof TRACE_PROBLEMS) => (problems.includes(name) ? TRACE_PROBLEMS[name] : null);

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: AUDIT_HEADING, to: AUDIT_PATH }, { label: TRACE_HEADING }]} title={TRACE_HEADING} lede={TRACE_LEDE} />
      <SectionCard title={TRACE_FORM_LABEL}>
        <form aria-label={TRACE_FORM_LABEL} className="flex min-w-0 flex-col gap-3" onSubmit={onRead} noValidate>
          <Field label="Trace id" hint={TRACE_HINTS.traceId} problem={problem("traceId")}>
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                maxLength={TRACE_ID_CHARS}
                className="font-mono"
                aria-describedby={describedBy}
                aria-invalid={invalid || undefined}
                value={traceId}
                onChange={(event) => {
                  setTraceId(event.target.value);
                }}
              />
            )}
          </Field>
          <Field label="Why you are reading it" hint={TRACE_HINTS.reason} problem={problem("reason")}>
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                maxLength={READ_REASON_CHARS}
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
            <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
              {READ_TRACE_LABEL}
            </Button>
          </div>
        </form>
      </SectionCard>
      {busy ? (
        <p role="status" className="m-0 text-[12.5px] text-dim">
          {READING_TRACE}
        </p>
      ) : null}
      {unreadable ? (
        <p role="status" className="m-0 text-[12.5px] text-body">
          {UNREADABLE_TRACE}
        </p>
      ) : null}
      {read === "" || (run === null && failure === null) ? null : (
        <SectionCard title={`Trace ${read}`}>
          <TraceGraph caption={`The steps of run ${read}`} run={run} failure={failure} busy={busy} />
        </SectionCard>
      )}
    </div>
  );
}
