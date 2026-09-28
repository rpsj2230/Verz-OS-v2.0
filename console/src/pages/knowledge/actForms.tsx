/**
 * The four acts on a document, each drawn in a drawer from its page's header: verify, add a newer
 * version, ask for the whole company, and hand to another steward (M7.4.4, M7.4.5, M7.4.6, M7.7.2).
 *
 * **A write that replaces something is confirmed first, in a sentence about what it replaces.** A
 * newer version replaces the one answers are drawn from, and a hand-over replaces the steward, so
 * both open `kit/ConfirmDialog` and send from its confirmation. Verifying and asking for the whole
 * company end nothing and send from the form (`tests/destructive-confirmed.test.ts`).
 *
 * **Nothing here decides who may do what.** A form is drawn only for an act the API offered on this
 * document, and the API decides the act again when it arrives.
 *
 * Task ids: M7.4.4, M7.4.5, M7.4.6, M7.7.2, M27.15.40
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog } from "../../components/kit";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import {
  defaultReviewDay,
  instantOf,
  LIFECYCLE_FIELDS,
  newVersionPath,
  promotionPath,
  stewardPath,
  verificationPath,
} from "../knowledgeLifecycleQuery";
import {
  ADD_VERSION,
  ASK_COMPANY,
  Field,
  FILE_LABEL,
  FORM,
  HAND_OVER,
  HAND_OVER_CONSEQUENCE,
  NEW_VERSION_CONSEQUENCE,
  PROBLEMS,
  REASON_HINT,
  REASON_LABEL,
  ReviewField,
  reviewProblem,
  STEWARD_HINT,
  STEWARD_LABEL,
  Submit,
  VERIFY,
} from "./formParts";

// ------------------------------------------------------------------ the acts on a document (K2)
/** Verify with the next review date (M7.4.6). */
export function VerifyForm({ itemId, onDone }: { readonly itemId: string; readonly onDone: () => void }) {
  const [day, setDay] = useState(defaultReviewDay());
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const problem = reviewProblem(day);
    setProblems(problem === null ? [] : [problem]);
    const instant = instantOf(day);
    if (problem !== null || instant === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(verificationPath(itemId), { method: "POST", body: { review_by: instant } });
      setBusy(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  return (
    <form className={FORM} aria-label="Verify this document" onSubmit={onSubmit} noValidate>
      {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
      <ReviewField value={day} onChange={setDay} problems={problems} />
      <Submit label={VERIFY} busy={busy} />
    </form>
  );
}

/** The media type a newer version is sent as, from its name. The API checks it against the bytes. */
export function versionType(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith(".pdf")) {
    return "application/pdf";
  }
  if (lower.endsWith(".docx")) {
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  }
  return lower.endsWith(".txt") ? "text/plain" : "text/markdown";
}

/** Add a newer version, confirmed first (M7.4.5). */
export function NewVersionForm({ itemId, title, onDone }: { readonly itemId: string; readonly title: string; readonly onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [day, setDay] = useState(defaultReviewDay());
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = [...(file === null ? [PROBLEMS.file] : []), ...[reviewProblem(day)].filter((one): one is string => one !== null)];
    setProblems(found);
    setConfirming(found.length === 0);
  };

  const send = () => {
    const instant = instantOf(day);
    if (file === null || instant === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(newVersionPath(itemId, instant), {
        method: "POST",
        file: { body: file, type: versionType(file.name), name: file.name },
      });
      setBusy(false);
      setConfirming(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  return (
    <>
      <form className={FORM} aria-label="Add a newer version" onSubmit={onSubmit} noValidate>
        {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
        <Field
          label={FILE_LABEL}
          hint="Plain text, Markdown, PDF or Word (.txt, .md, .pdf, .docx), read the way an upload is."
          problems={problems.filter((one) => one === PROBLEMS.file)}
        >
          {(id, describedBy) => (
            <Input
              id={id}
              type="file"
              name="file"
              className="h-11 sm:h-9"
              aria-describedby={describedBy}
              accept=".md,.markdown,.txt,.pdf,.docx"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
              }}
            />
          )}
        </Field>
        <ReviewField value={day} onChange={setDay} problems={problems.filter((one) => one !== PROBLEMS.file)} />
        <Submit label={ADD_VERSION} busy={busy} />
      </form>
      <ConfirmDialog
        open={confirming}
        question={`Replace ${title} with ${file?.name ?? "the chosen file"}?`}
        consequence={NEW_VERSION_CONSEQUENCE}
        confirmLabel={ADD_VERSION}
        cancelLabel="Keep the current version"
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </>
  );
}

/** Ask for the whole company, which waits on the Approvals screen (M7.4.4). */
export function ProposeForm({ itemId, waits, onDone }: { readonly itemId: string; readonly waits: string | undefined; readonly onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [day, setDay] = useState(defaultReviewDay());
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = [...(reason.trim() === "" ? [PROBLEMS.reason] : []), ...[reviewProblem(day)].filter((one): one is string => one !== null)];
    setProblems(found);
    const instant = instantOf(day);
    if (found.length > 0 || instant === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(promotionPath(itemId), {
        method: "POST",
        body: { review_by: instant, reason: reason.trim() },
      });
      setBusy(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  return (
    <form className={FORM} aria-label="Ask for the whole company" onSubmit={onSubmit} noValidate>
      {waits === undefined ? null : <p className="m-0 text-[12.5px] leading-snug text-dim">{waits}</p>}
      {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
      <Field label={REASON_LABEL} hint={REASON_HINT} problems={problems.filter((one) => one === PROBLEMS.reason)}>
        {(id, describedBy) => (
          <Textarea
            id={id}
            name="reason"
            maxLength={500}
            aria-describedby={describedBy}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
            }}
          />
        )}
      </Field>
      <ReviewField value={day} onChange={setDay} problems={problems.filter((one) => one !== PROBLEMS.reason)} />
      <Submit label={ASK_COMPANY} busy={busy} />
    </form>
  );
}

/** Hand to another steward, confirmed first (M7.7.2). */
export function HandOverForm({ itemId, title, onDone }: { readonly itemId: string; readonly title: string; readonly onDone: () => void }) {
  const [to, setTo] = useState("");
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = to.trim() === "" ? [PROBLEMS.steward] : [];
    setProblems(found);
    setConfirming(found.length === 0);
  };

  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(stewardPath(itemId), { method: "POST", body: { steward_id: to.trim() } });
      setBusy(false);
      setConfirming(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  return (
    <>
      <form className={FORM} aria-label="Hand to another steward" onSubmit={onSubmit} noValidate>
        {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
        <Field label={STEWARD_LABEL} hint={STEWARD_HINT} problems={problems}>
          {(id, describedBy) => (
            <Input
              id={id}
              type="text"
              name="steward_id"
              className="h-11 sm:h-9"
              maxLength={128}
              aria-describedby={describedBy}
              value={to}
              onChange={(event) => {
                setTo(event.target.value);
              }}
            />
          )}
        </Field>
        <Submit label={HAND_OVER} busy={busy} />
      </form>
      <ConfirmDialog
        open={confirming}
        question={`Hand ${title} to ${to.trim()}?`}
        consequence={HAND_OVER_CONSEQUENCE}
        confirmLabel={HAND_OVER}
        cancelLabel="Keep the current steward"
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </>
  );
}

