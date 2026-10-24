/**
 * Taking a report out of the system from the screen whose rows it holds: the reason as a closed
 * word, the reference as a token, a confirmation naming what leaves, and the file saved once the
 * server has recorded it on the Exports log.
 *
 * **The route decides what the file holds and records that it left.** It builds the document from
 * exactly the rows the screen would show this reader, writes `ops.data_export` (whose trigger writes
 * the ledger entry) under their name with the reason and reference given, and hands the document over
 * only after that record has committed. The file names no row it leaves out and carries no count of
 * them. This component sends the request and saves the file, and decides nothing about either.
 *
 * **One component for every report taken this way**, so the access certification report and the
 * knowledge inventory ask the same two things in the same words, check them the same way before
 * anything is sent, and say the same when the file cannot be saved. It was the certification report's
 * own form until the second report arrived (M25.3.3); the words each screen adds are its props.
 *
 * **The call is the screen's, not this form's.** Each report passes `send`, which spells its own
 * route, so the write sits in the file of the screen that sends it and the console audit reads which
 * screen reaches which route from the source, as it does for every other write. A path passed as a
 * prop would have made every screen reach every report. Because the form itself holds no call, the
 * blank form is held by the screens' own tests (`tests/review-pages.test.tsx`,
 * `tests/knowledge-page.test.tsx`).
 *
 * **The reason is a closed word and the reference a token**, for
 * `brain.ops.export.A_REASON_A_CALLER_CAN_OMIT_IS_A_REASON_NOBODY_GIVES`' reason, and the form says
 * what each takes before anything is sent. Blank fields are said beside them, and only a complete
 * request is confirmed.
 *
 * Task ids: M27.15.21, M25.3.3, M27.16.1
 */

import { Download } from "lucide-react";
import { useState, type FormEvent } from "react";
import type { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, Drawer, FailureState, Note, saveCsv } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Field, NativeSelect } from "../access/formParts";
import { CANNOT_SAVE, readTaken, REASON_LABELS, reasonLabel } from "../dataTransferQuery";

export const REASON_HINT = "Why the report is leaving the system. Chosen from a fixed list and kept with the record.";
export const REFERENCE_HINT =
  "A ticket or matter number: letters, digits and . _ / # -, no spaces, up to 64 characters, for example AUDIT-2026-Q3. Never a person's name.";
export const REVIEW_EXPORT = "Review the export";
export const KEEP_IT = "Not now";
export const REASON_BLANK = "Choose why the report is leaving the system.";
export const REFERENCE_BLANK = "Give the ticket or matter number the report is for.";
export const REFERENCE_SHAPE = "Use letters, digits and . _ / # - only, with no spaces, starting with a letter or a digit.";

/** `brain.tables.data_export.REFERENCE_PATTERN`, held equal by `tests/review-pages.test.tsx`. */
export const REFERENCE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_./#-]{0,63}$/;

/** The reasons an export may be taken for, as `brain.ops.export.ExportReason` declares them. */
export const EXPORT_REASONS: readonly string[] = Object.keys(REASON_LABELS);

/** What the API answered to the request, as `request` returns it. */
export type Sent = Awaited<ReturnType<typeof request<unknown>>>;

/** What every report is asked for: why it is leaving, and the ticket or matter it is for. */
export interface ReportAsked {
  readonly reason: string;
  readonly reason_reference: string;
}

export interface ReportExportProps {
  /**
   * Sends the request to the route that builds, records and hands over the report. Each report
   * spells its own call, so a screen's write is found at the screen's own file and the console audit
   * says which route which screen reaches, and not that one form reaches them all.
   */
  readonly send: (asked: ReportAsked) => Promise<Sent>;
  /** What the button, the drawer and the confirmation's act are called. */
  readonly label: string;
  /** The drawer's one-line description of what the file holds. */
  readonly description: string;
  /** The confirmation's question. */
  readonly question: string;
  /** The confirmation's consequence: what leaves, where it is recorded, that it is not kept. */
  readonly consequence: string;
  /** The id the form is given, so the drawer's footer can submit it. */
  readonly formId: string;
}

export function ReportExport({ send, label, description, question, consequence, formId }: ReportExportProps) {
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

  const sendIt = () => {
    setBusy(true);
    void (async () => {
      const result = await send({ reason, reason_reference: reference.trim() });
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
        <Download aria-hidden /> {label}
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
        title={label}
        description={description}
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
            <Button type="submit" form={formId} disabled={busy}>
              {REVIEW_EXPORT}
            </Button>
          </>
        }
      >
        <form id={formId} aria-label={label} className="flex min-w-0 flex-col gap-4" noValidate onSubmit={ask}>
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
          question={question}
          consequence={consequence}
          confirmLabel={label}
          cancelLabel={KEEP_IT}
          busy={busy}
          onConfirm={sendIt}
          onCancel={() => {
            setConfirming(false);
          }}
        />
      </Drawer>
    </>
  );
}
