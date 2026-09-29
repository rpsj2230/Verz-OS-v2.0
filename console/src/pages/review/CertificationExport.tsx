/**
 * Exporting the access certification report (M27.15.21): every grant and pack the reviewer may
 * decide, with who holds it, who granted it, when it lapses and its last review, as a file.
 *
 * **The route decides what the file holds and records that it left.** `POST
 * /govern/access-review/export` builds the document from exactly the rows the review screen would
 * show this reviewer, records it on the Exports log (`ops.data_export`, whose trigger writes the
 * ledger entry) under their name with the reason and reference given, and hands the document over
 * only after that record has committed. The file names no row it leaves out and carries no count of
 * them.
 *
 * **The reason is a closed word and the reference a token**, for
 * `brain.ops.export.A_REASON_A_CALLER_CAN_OMIT_IS_A_REASON_NOBODY_GIVES`' reason, and the form says
 * what each takes before anything is sent. Blank fields are said beside them, and only a complete
 * request is confirmed.
 *
 * Task ids: M27.15.21, M27.16.1
 */

import { Download } from "lucide-react";
import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, Drawer, FailureState, Note, saveCsv } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Field, NativeSelect } from "../access/formParts";
import { CANNOT_SAVE, readTaken, REASON_LABELS, reasonLabel } from "../dataTransferQuery";
import { ACT_LABELS } from "./reviewActions";

export const CERTIFICATION_EXPORT_API_PATH = "/govern/access-review/export";

export const EXPORT_DESCRIPTION =
  "A file of every grant listed on this screen with its last review, for whoever certifies access. It is recorded on the Exports log under your name.";
export const REASON_HINT = "Why the report is leaving the system. Chosen from a fixed list and kept with the record.";
export const REFERENCE_HINT =
  "A ticket or matter number: letters, digits and . _ / # -, no spaces, up to 64 characters, for example AUDIT-2026-Q3. Never a person's name.";
export const REVIEW_EXPORT = "Review the export";
export const KEEP_IT = "Not now";
export const EXPORT_QUESTION = "Export the access certification report?";
export const EXPORT_CONSEQUENCE =
  "The file holds every grant you may review, with who holds it, who granted it and its last review. It is recorded on the Exports log under your name with this reason and reference, and is not kept on the server.";
export const REASON_BLANK = "Choose why the report is leaving the system.";
export const REFERENCE_BLANK = "Give the ticket or matter number the report is for.";
export const REFERENCE_SHAPE = "Use letters, digits and . _ / # - only, with no spaces, starting with a letter or a digit.";

/** `brain.tables.data_export.REFERENCE_PATTERN`, held equal by `tests/review-pages.test.tsx`. */
export const REFERENCE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_./#-]{0,63}$/;

/** The reasons an export may be taken for, as `brain.ops.export.ExportReason` declares them. */
export const EXPORT_REASONS: readonly string[] = Object.keys(REASON_LABELS);

const FORM = "certification-export";

export function CertificationExport() {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [problems, setProblems] = useState<{ reason: string | null; reference: string | null }>({ reason: null, reference: null });
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const typed = reference.trim();
    const found = {
      reason: reason === "" ? REASON_BLANK : null,
      reference: typed === "" ? REFERENCE_BLANK : REFERENCE_PATTERN.test(typed) ? null : REFERENCE_SHAPE,
    };
    setProblems(found);
    setFailure(null);
    if (found.reason === null && found.reference === null) {
      setConfirming(true);
    }
  };

  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(CERTIFICATION_EXPORT_API_PATH, {
        method: "POST",
        body: { reason, reason_reference: reference.trim() },
      });
      setBusy(false);
      setConfirming(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const taken = readTaken(result.data);
      if (taken === null) {
        return;
      }
      setTold(saveCsv(taken.filename, taken.document) ? taken.told : CANNOT_SAVE);
      setOpen(false);
      setReason("");
      setReference("");
    })();
  };

  return (
    <>
      <Button
        size="sm"
        className="min-h-11 sm:min-h-8"
        onClick={() => {
          setTold(null);
          setOpen(true);
        }}
      >
        <Download aria-hidden /> {ACT_LABELS.exportReport}
      </Button>
      {told === null ? null : (
        <span role="status" className="basis-full">
          <Note kind="works">{told}</Note>
        </span>
      )}
      <Drawer
        open={open}
        onOpenChange={(next) => {
          if (!next && !busy) {
            setOpen(false);
          }
        }}
        title={ACT_LABELS.exportReport}
        description={EXPORT_DESCRIPTION}
        footer={
          <>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setOpen(false);
              }}
            >
              {KEEP_IT}
            </Button>
            <Button type="submit" form={FORM} disabled={busy}>
              {REVIEW_EXPORT}
            </Button>
          </>
        }
      >
        <form id={FORM} aria-label={ACT_LABELS.exportReport} className="flex min-w-0 flex-col gap-4" noValidate onSubmit={ask}>
          {failure === null ? null : <FailureState failure={failure} />}
          <Field label="Reason" hint={REASON_HINT} problem={problems.reason} apiProblems={failure?.problems ?? []} names={["reason"]}>
            {(ids) => (
              <NativeSelect {...ids} value={reason} onChange={setReason}>
                <option value="">Choose a reason</option>
                {EXPORT_REASONS.map((one) => (
                  <option key={one} value={one}>
                    {reasonLabel(one)}
                  </option>
                ))}
              </NativeSelect>
            )}
          </Field>
          <Field
            label="Reference"
            hint={REFERENCE_HINT}
            problem={problems.reference}
            apiProblems={failure?.problems ?? []}
            names={["reason_reference"]}
          >
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                name="reason_reference"
                maxLength={64}
                autoComplete="off"
                aria-describedby={describedBy === "" ? undefined : describedBy}
                aria-invalid={invalid || undefined}
                value={reference}
                onChange={(event) => {
                  setReference(event.target.value);
                }}
              />
            )}
          </Field>
        </form>
        <ConfirmDialog
          open={confirming}
          question={EXPORT_QUESTION}
          consequence={EXPORT_CONSEQUENCE}
          confirmLabel={ACT_LABELS.exportReport}
          cancelLabel={KEEP_IT}
          busy={busy}
          onConfirm={send}
          onCancel={() => {
            setConfirming(false);
          }}
        />
      </Drawer>
    </>
  );
}
