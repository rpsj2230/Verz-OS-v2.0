/**
 * The writes of Retention, legal holds and erasure: releasing the sweep and putting it back to
 * reporting, placing and lifting a legal hold, and filing an erasure request.
 *
 * **Each is confirmed, and each confirmation says what will happen in the API's words** (the
 * controls answer's `releasing`, `withdrawing`, `holding`, `lifting` and `erasing`). A release names
 * the counts from the report on the page first. **Every form says what it takes before it is sent**,
 * and a form with a problem names it beside the fields and opens no confirmation; the API judges it
 * again. A success says what the database recorded and when, and the page reads everything again.
 *
 * **Nothing here decides who may act.** `may_release`, `may_hold` and `may_erase` came from the
 * retention module's own functions on the server and only decide whether a control is drawn; the
 * write route decides again.
 *
 * Task ids: M27.7.24, M27.16.1
 */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, Drawer, FailureState, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { Field, FormProblem } from "../access/formParts";
import {
  EMPTY_ERASURE,
  EMPTY_HOLD,
  ERASURES_API_PATH,
  erasureBody,
  erasureProblems,
  HOLD_API_PATH,
  holdBody,
  holdProblems,
  holdQuestion,
  LIFT_API_PATH,
  liftProblems,
  releaseCounts,
  RELEASE_API_PATH,
  WITHDRAWAL_API_PATH,
  type Controls,
  type ErasureBody,
  type ErasureForm,
  type HoldBody,
  type HoldForm,
  type Report,
} from "../retentionQuery";
import { whenWords } from "../review/parts";

export const RELEASE_LABEL = "Release the sweep";
export const KEEP_REPORTING = "Keep it reporting";
export const WITHDRAW_LABEL = "Put the sweep back to reporting";
export const LEAVE_RELEASED = "Leave it released";
export const PLACE_LABEL = "Place hold";
export const DO_NOT_PLACE = "Do not place it";
export const LIFT_LABEL = "Lift hold";
export const KEEP_HOLD = "Keep the hold";
export const FILE_ERASURE_LABEL = "File the erasure request";
export const DO_NOT_FILE = "Do not file it";
export const REVIEW_HOLD = "Review the hold";
export const REVIEW_REQUEST = "Review the request";
export const HOLD_FORM_LABEL = "Place a legal hold";
export const LIFT_FORM_LABEL = "Lift a legal hold";
export const ERASURE_FORM_LABEL = "Ask for somebody's data to be erased";

export const HOLD_HINTS = Object.freeze({
  holdId: "A reference with no spaces, up to 128 letters, digits and . _ @ -, such as the matter number it is for.",
  reasonCode: "A code in lower case with underscores or dots, such as litigation or regulator.request. Never a name.",
  subjects: "The references of the people whose data it holds, as the People page shows them, separated by spaces, commas or lines.",
  actors: "The references of the people whose actions it holds, the same way.",
});

export const ERASURE_HINTS = Object.freeze({
  subject: "The reference of the person whose data is to be erased, exactly as the People page shows it, with no spaces.",
  reference: "The matter or ticket the request arrived under, such as DSAR-2019/004: letters, digits and . _ / # -, no spaces, no names.",
});

function stamp(payload: unknown, key: string): string {
  const at = typeof payload === "object" && payload !== null ? (payload as Record<string, unknown>)[key] : undefined;
  return typeof at === "string" ? at : "";
}

/** One write in flight, its refusal, and what the page was told. */
export function useRetentionWrite(onDone: (told: string) => void) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const send = useCallback(
    (path: string, body: unknown, told: (payload: unknown) => string, after: () => void) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(path, { method: "POST", body });
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

/** Release the sweep, or put it back to reporting, each from its confirmation. */
export function SweepActs({ report, controls, onDone }: { readonly report: Report; readonly controls: Controls; readonly onDone: (told: string) => void }) {
  const [confirming, setConfirming] = useState<"release" | "withdraw" | null>(null);
  const write = useRetentionWrite(onDone);
  const releasable = report.report_only && report.failure === null && !report.released;
  if (!controls.may_release || (!report.released && !releasable)) {
    return null;
  }
  return (
    <>
      <Button
        size="sm"
        variant={report.released ? "outline" : "default"}
        className="min-h-11 sm:min-h-8"
        disabled={write.busy}
        onClick={() => {
          write.setFailure(null);
          setConfirming(report.released ? "withdraw" : "release");
        }}
      >
        {report.released ? WITHDRAW_LABEL : RELEASE_LABEL}
      </Button>
      {write.failure === null ? null : <FailureState failure={write.failure} />}
      <ConfirmDialog
        open={confirming === "release"}
        question={`Release the sweep after the report of ${whenWords(report.at)}?`}
        consequence={`${releaseCounts(report, whenWords(report.at))} ${controls.releasing}`}
        confirmLabel={RELEASE_LABEL}
        cancelLabel={KEEP_REPORTING}
        busy={write.busy}
        onConfirm={() => {
          write.send(RELEASE_API_PATH, { after_report: report.report_id }, (payload) => `The sweep was released at ${whenWords(stamp(payload, "released_at"))}.`, () => {
            setConfirming(null);
          });
        }}
        onCancel={() => {
          setConfirming(null);
        }}
      />
      <ConfirmDialog
        open={confirming === "withdraw"}
        question="Put the sweep back to reporting?"
        consequence={controls.withdrawing}
        confirmLabel={WITHDRAW_LABEL}
        cancelLabel={LEAVE_RELEASED}
        busy={write.busy}
        onConfirm={() => {
          write.send(WITHDRAWAL_API_PATH, undefined, (payload) => `The sweep was put back to reporting at ${whenWords(stamp(payload, "withdrawn_at"))}.`, () => {
            setConfirming(null);
          });
        }}
        onCancel={() => {
          setConfirming(null);
        }}
      />
    </>
  );
}

function Problems({ problems }: { readonly problems: readonly string[] }) {
  if (problems.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col gap-1">
      {problems.map((one) => (
        <FormProblem key={one}>{one}</FormProblem>
      ))}
    </div>
  );
}

/** The drawer a legal hold is placed from. */
export function HoldDrawer({ controls, onClose, onDone }: { readonly controls: Controls; readonly onClose: () => void; readonly onDone: (told: string) => void }) {
  const [form, setForm] = useState<HoldForm>(EMPTY_HOLD);
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [placing, setPlacing] = useState<HoldBody | null>(null);
  const write = useRetentionWrite(onDone);
  const apiProblems = write.failure?.problems ?? [];
  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = holdProblems(form);
    setProblems(found);
    if (found.length === 0) {
      write.setFailure(null);
      setPlacing(holdBody(form));
    }
  };
  const text = (name: "holdId" | "reasonCode", label: string, api: string) => (
    <Field label={label} hint={HOLD_HINTS[name]} apiProblems={apiProblems} names={[api]}>
      {({ id, describedBy, invalid }) => (
        <Input
          id={id}
          name={api}
          autoComplete="off"
          aria-describedby={describedBy === "" ? undefined : describedBy}
          aria-invalid={invalid || undefined}
          value={form[name]}
          onChange={(event) => {
            setForm({ ...form, [name]: event.target.value });
          }}
        />
      )}
    </Field>
  );
  const people = (name: "subjects" | "actors", label: string) => (
    <Field label={label} hint={HOLD_HINTS[name]} apiProblems={apiProblems} names={[name]}>
      {({ id, describedBy, invalid }) => (
        <Textarea
          id={id}
          name={name}
          aria-describedby={describedBy === "" ? undefined : describedBy}
          aria-invalid={invalid || undefined}
          value={form[name]}
          onChange={(event) => {
            setForm({ ...form, [name]: event.target.value });
          }}
        />
      )}
    </Field>
  );
  return (
    <Drawer
      open
      onOpenChange={(next) => {
        if (!next && !write.busy) {
          onClose();
        }
      }}
      title={HOLD_FORM_LABEL}
      description="Stops the sweep and erasure touching what it covers until it is lifted."
      footer={
        <>
          <Button variant="outline" disabled={write.busy} onClick={onClose}>
            {DO_NOT_PLACE}
          </Button>
          <Button type="submit" form="hold-form" disabled={write.busy}>
            {REVIEW_HOLD}
          </Button>
        </>
      }
    >
      <form id="hold-form" aria-label={HOLD_FORM_LABEL} className="flex min-w-0 flex-col gap-4" noValidate onSubmit={ask}>
        {write.failure === null ? null : <FailureState failure={write.failure} />}
        {text("holdId", "Reference", "hold_id")}
        {text("reasonCode", "Reason code", "reason_code")}
        {people("subjects", "People it covers")}
        {people("actors", "People whose actions it covers")}
        <label className="flex min-h-11 items-center gap-2 text-[13px] text-ink sm:min-h-8">
          <input
            type="checkbox"
            name="all_subjects"
            checked={form.everybody}
            onChange={(event) => {
              setForm({ ...form, everybody: event.target.checked });
            }}
          />
          Hold everybody
        </label>
        <Problems problems={problems} />
      </form>
      <ConfirmDialog
        open={placing !== null}
        question={placing === null ? "" : holdQuestion(placing)}
        consequence={controls.holding}
        confirmLabel={PLACE_LABEL}
        cancelLabel={DO_NOT_PLACE}
        busy={write.busy}
        onConfirm={() => {
          if (placing !== null) {
            const body = placing;
            write.send(HOLD_API_PATH, body, (payload) => `Legal hold ${body.hold_id} was placed at ${whenWords(stamp(payload, "placed_at"))}.`, () => {
              setPlacing(null);
            });
          }
        }}
        onCancel={() => {
          setPlacing(null);
        }}
      />
    </Drawer>
  );
}

/** Lifting one hold by its reference, from its confirmation. */
export function useLift(controls: Controls | null, onDone: (told: string) => void): { readonly lift: (holdId: string) => void; readonly drawn: ReactNode; readonly busy: boolean } {
  const [lifting, setLifting] = useState<string | null>(null);
  const write = useRetentionWrite(onDone);
  const drawn = (
    <>
      {write.failure === null ? null : <FailureState failure={write.failure} />}
      <ConfirmDialog
        open={lifting !== null}
        question={`Lift legal hold ${lifting ?? ""}?`}
        consequence={controls?.lifting ?? ""}
        confirmLabel={LIFT_LABEL}
        cancelLabel={KEEP_HOLD}
        busy={write.busy}
        onConfirm={() => {
          if (lifting !== null) {
            const holdId = lifting;
            write.send(LIFT_API_PATH, { hold_id: holdId }, (payload) => `Legal hold ${holdId} was lifted at ${whenWords(stamp(payload, "lifted_at"))}.`, () => {
              setLifting(null);
            });
          }
        }}
        onCancel={() => {
          setLifting(null);
        }}
      />
    </>
  );
  return {
    lift: (holdId: string) => {
      write.setFailure(null);
      setLifting(holdId);
    },
    drawn,
    busy: write.busy,
  };
}

/** The drawer a hold not on the list yet is lifted from, by the reference it was placed under. */
export function LiftDrawer({ cited, onClose, onLift }: { readonly cited: readonly string[]; readonly onClose: () => void; readonly onLift: (holdId: string) => void }) {
  const [holdId, setHoldId] = useState("");
  const [problems, setProblems] = useState<readonly string[]>([]);
  return (
    <Drawer
      open
      onOpenChange={(next) => {
        if (!next) {
          onClose();
        }
      }}
      title={LIFT_FORM_LABEL}
      description="For a hold placed since the newest report, which the list does not show yet."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            {KEEP_HOLD}
          </Button>
          <Button type="submit" form="lift-form">
            {LIFT_LABEL}
          </Button>
        </>
      }
    >
      <form
        id="lift-form"
        aria-label={LIFT_FORM_LABEL}
        className="flex min-w-0 flex-col gap-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          const found = liftProblems(holdId.trim());
          setProblems(found);
          if (found.length === 0) {
            onLift(holdId.trim());
          }
        }}
      >
        <Field label="Reference of the hold" hint="Exactly as it was placed, with no spaces.">
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              name="hold_id"
              list="cited-holds"
              autoComplete="off"
              aria-describedby={describedBy === "" ? undefined : describedBy}
              aria-invalid={invalid || undefined}
              value={holdId}
              onChange={(event) => {
                setHoldId(event.target.value);
              }}
            />
          )}
        </Field>
        <datalist id="cited-holds">
          {cited.map((one) => (
            <option key={one} value={one} />
          ))}
        </datalist>
        <Problems problems={problems} />
      </form>
    </Drawer>
  );
}

/** The drawer an erasure request is filed from. */
export function ErasureDrawer({ controls, onClose, onDone }: { readonly controls: Controls; readonly onClose: () => void; readonly onDone: (told: string) => void }) {
  const [form, setForm] = useState<ErasureForm>(EMPTY_ERASURE);
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [filing, setFiling] = useState<ErasureBody | null>(null);
  const write = useRetentionWrite(onDone);
  const apiProblems = write.failure?.problems ?? [];
  return (
    <Drawer
      open
      onOpenChange={(next) => {
        if (!next && !write.busy) {
          onClose();
        }
      }}
      title={ERASURE_FORM_LABEL}
      description="Removes and retires what the system holds about one person, store by store."
      footer={
        <>
          <Button variant="outline" disabled={write.busy} onClick={onClose}>
            {DO_NOT_FILE}
          </Button>
          <Button type="submit" form="erasure-form" disabled={write.busy}>
            {REVIEW_REQUEST}
          </Button>
        </>
      }
    >
      <form
        id="erasure-form"
        aria-label={ERASURE_FORM_LABEL}
        className="flex min-w-0 flex-col gap-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          const found = erasureProblems(form);
          setProblems(found);
          if (found.length === 0) {
            write.setFailure(null);
            setFiling(erasureBody(form));
          }
        }}
      >
        {write.failure === null ? null : <FailureState failure={write.failure} />}
        <Field label="Person, by reference" hint={ERASURE_HINTS.subject} apiProblems={apiProblems} names={["subject_id"]}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              name="subject_id"
              autoComplete="off"
              aria-describedby={describedBy === "" ? undefined : describedBy}
              aria-invalid={invalid || undefined}
              value={form.subject}
              onChange={(event) => {
                setForm({ ...form, subject: event.target.value });
              }}
            />
          )}
        </Field>
        <Field label="Matter or ticket reference" hint={ERASURE_HINTS.reference} apiProblems={apiProblems} names={["reason_reference"]}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              name="reason_reference"
              autoComplete="off"
              aria-describedby={describedBy === "" ? undefined : describedBy}
              aria-invalid={invalid || undefined}
              value={form.reference}
              onChange={(event) => {
                setForm({ ...form, reference: event.target.value });
              }}
            />
          )}
        </Field>
        <Problems problems={problems} />
      </form>
      <ConfirmDialog
        open={filing !== null}
        question={filing === null ? "" : `File a request to erase ${filing.subject_id}'s data?`}
        consequence={controls.erasing}
        confirmLabel={FILE_ERASURE_LABEL}
        cancelLabel={DO_NOT_FILE}
        busy={write.busy}
        onConfirm={() => {
          if (filing !== null) {
            const body = filing;
            write.send(ERASURES_API_PATH, body, (payload) => `The request to erase ${body.subject_id}'s data was filed at ${whenWords(stamp(payload, "requested_at"))}.`, () => {
              setFiling(null);
              setForm(EMPTY_ERASURE);
            });
          }
        }}
        onCancel={() => {
          setFiling(null);
        }}
      />
    </Drawer>
  );
}

/** What the page was told about the last write, drawn under its header. */
export function Told({ told }: { readonly told: string | null }) {
  return told === null ? null : (
    <div role="status">
      <Note kind="works">{told}</Note>
    </div>
  );
}
