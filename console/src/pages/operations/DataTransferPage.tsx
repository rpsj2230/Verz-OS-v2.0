/**
 * Import and export, on the page kit: the audit trail exported as a confirmed act, the exports you
 * have taken, and every data set the product can move with whether it can move today.
 *
 * **Taking an export is confirmed, and the confirmation says what an export is.** The question
 * names the days and the reason; the consequence is the API's two sentences about a copy that leaves
 * every guard behind and a document handed over once. The document is saved as a file when the
 * answer arrives and is never drawn on the screen.
 *
 * **The form says what it accepts before it is sent**: a reason from the API's list, a ticket or
 * matter number and never a name, and two days in UTC with the last included. Blank days are said
 * beside the fields and nothing is sent.
 *
 * **Nothing here decides who may export.** `exportable` only decides whether the form is drawn; the
 * route decides again before it reads anything.
 *
 * **Importing has no route**, so it is `kit/UnavailableAction` with the sentence
 * `operationsActions.ts` gives; the catalogue still lists every import the product knows with the
 * API's sentence for why it cannot run yet.
 *
 * **What was removed.** The breadcrumb as text, the file digest as a default column (a column a
 * reader turns on), and the per-row "Available." prefix (a pill now).
 *
 * Task ids: M27.8.16, M27.9.4, M27.16.1
 */

import { Download, Upload } from "lucide-react";
import { useCallback, useId, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Note, SectionCard, UnavailableAction, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  CANNOT_SAVE,
  chainSentence,
  DATA_TRANSFER_API_PATH,
  EXPORTS_API_PATH,
  exportBody,
  readDataTransfer,
  readTaken,
  reasonLabel,
  saveDocument,
  windowOf,
  windowSentence,
  type DataSetRow,
  type DataTransferBody,
  type ExportRecordRow,
} from "../dataTransferQuery";
import type { Problem } from "../webhooksQuery";
import { UNAVAILABLE } from "./operationsActions";
import { at, GOVERNANCE, Line, OpsPage, UNREADABLE, WholeList } from "./parts";
import { AvailablePill } from "./pills";

export const DATA_TRANSFER_HEADING = "Import and export";
export const DATA_TRANSFER_LEDE = "Take an export of the audit trail, see the exports you have taken, and what else can be moved in or out.";
export const READING_DATA_TRANSFER = "Loading what can be imported and exported.";
export const NOT_EXPORTABLE =
  "Taking an export needs the export grant over the whole company and the grant to open the audit trail.";
export const NO_EXPORTS = "You have not taken an export";
export const NO_EXPORTS_MORE = "An export you take appears here with its reason and its window.";
export const EXPORT_LABEL = "Export the audit trail";
export const KEEP_LABEL = "Change nothing";
export const NOT_A_WINDOW = "Choose a first and a last day.";
export const CATALOGUE_HEADING = "What can be moved";
export const NOTHING_TO_MOVE = "Nothing is listed";

const EXPORT_FIELDS: readonly string[] = ["reason", "reason_reference", "window", "since", "until", "data_set"];
const EXPORT_FORM = "data-export";
const WINDOW_NAMES: readonly string[] = ["window", "since", "until"];

const SELECT =
  "h-11 w-full min-w-0 rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring sm:h-9";

const CATALOGUE_COLUMNS: readonly EntityColumn<DataSetRow>[] = [
  { id: "data", header: "Data", hideable: false, cell: (row) => row.label, text: (row) => row.label },
  {
    id: "direction",
    header: "Direction",
    cell: (row) => (row.direction === "export" ? "Out" : "In"),
    text: (row) => row.direction,
  },
  { id: "carries", header: "What it carries", cell: (row) => row.carries, text: (row) => row.carries },
  {
    id: "today",
    header: "Today",
    cell: (row) => (
      <span className="flex flex-col gap-0.5">
        <AvailablePill runs={row.runs} />
        <span className="text-[12px] text-dim">{row.told}</span>
      </span>
    ),
    text: (row) => row.told,
  },
];

const EXPORT_COLUMNS: readonly EntityColumn<ExportRecordRow>[] = [
  { id: "taken", header: "Taken", hideable: false, cell: (row) => at(row.produced_at), text: (row) => row.produced_at },
  { id: "reason", header: "Reason", cell: (row) => reasonLabel(row.reason), text: (row) => reasonLabel(row.reason) },
  { id: "reference", header: "Reference", cell: (row) => row.reason_reference, text: (row) => row.reason_reference },
  { id: "window", header: "Window", cell: (row) => windowSentence(row), text: (row) => windowSentence(row) },
  { id: "chain", header: "Chain", cell: (row) => chainSentence(row), text: (row) => chainSentence(row) },
  {
    id: "digest",
    header: "File digest",
    hidden: true,
    cell: (row) => <code className="font-mono text-[12px]">{row.document_digest}</code>,
    text: (row) => row.document_digest,
  },
];

function ExportForm({ page, onTaken }: { readonly page: DataTransferBody; readonly onTaken: (sentence: string) => void }) {
  const [reason, setReason] = useState<string>(page.reasons[0] ?? "");
  const [reference, setReference] = useState("");
  const [firstDay, setFirstDay] = useState("");
  const [lastDay, setLastDay] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [blank, setBlank] = useState<Problem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const problems: readonly Problem[] = [...blank, ...(failure?.problems ?? [])];
  const ids = { reason: useId(), reference: useId(), first: useId(), last: useId() };

  const span = windowOf(firstDay, lastDay);

  const take = useCallback(() => {
    if (span === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(EXPORTS_API_PATH, {
        method: "POST",
        body: exportBody(reason, reference, span),
      });
      setBusy(false);
      setConfirming(false);
      if (!result.ok) {
        setBlank([]);
        setFailure(result.failure);
        return;
      }
      setBlank([]);
      setFailure(null);
      const taken = readTaken(result.data);
      if (taken === null) {
        onTaken(UNREADABLE);
        return;
      }
      const saved = saveDocument(taken.filename, taken.document, document);
      onTaken(saved ? taken.told : CANNOT_SAVE);
    })();
  }, [onTaken, reason, reference, span]);

  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFailure(null);
    if (span === null) {
      setBlank([{ field: "window", code: "no_window", message: NOT_A_WINDOW }]);
      return;
    }
    setConfirming(true);
  }

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} fields={EXPORT_FIELDS} />}
      <form aria-label={EXPORT_LABEL} className="flex min-w-0 flex-col gap-3" onSubmit={ask}>
        <div className="[display:grid] min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-1">
            <label htmlFor={ids.reason} className="text-[13px] font-medium text-ink">
              Reason
            </label>
            <select
              id={ids.reason}
              className={SELECT}
              name="reason"
              value={reason}
              {...problemAttributes(problems, EXPORT_FORM, "reason")}
              onChange={(event) => {
                setReason(event.target.value);
              }}
            >
              {page.reasons.map((one) => (
                <option key={one} value={one}>
                  {reasonLabel(one)}
                </option>
              ))}
            </select>
            <FieldProblems problems={problems} form={EXPORT_FORM} names="reason" />
          </div>
          <div className="flex min-w-0 flex-col gap-1">
            <label htmlFor={ids.reference} className="text-[13px] font-medium text-ink">
              Reference of the written request
            </label>
            <Input
              id={ids.reference}
              type="text"
              name="reason_reference"
              value={reference}
              {...problemAttributes(problems, EXPORT_FORM, "reason_reference")}
              onChange={(event) => {
                setReference(event.target.value);
              }}
            />
            <span className="text-[12px] text-dim">A ticket or matter number. Never a person&apos;s name.</span>
            <FieldProblems problems={problems} form={EXPORT_FORM} names="reason_reference" />
          </div>
          <div className="flex min-w-0 flex-col gap-1">
            <label htmlFor={ids.first} className="text-[13px] font-medium text-ink">
              First day
            </label>
            <Input
              id={ids.first}
              type="date"
              name="since"
              value={firstDay}
              {...problemAttributes(problems, EXPORT_FORM, WINDOW_NAMES)}
              onChange={(event) => {
                setFirstDay(event.target.value);
              }}
            />
          </div>
          <div className="flex min-w-0 flex-col gap-1">
            <label htmlFor={ids.last} className="text-[13px] font-medium text-ink">
              Last day
            </label>
            <Input
              id={ids.last}
              type="date"
              name="until"
              value={lastDay}
              {...problemAttributes(problems, EXPORT_FORM, WINDOW_NAMES)}
              onChange={(event) => {
                setLastDay(event.target.value);
              }}
            />
          </div>
        </div>
        <FieldProblems problems={problems} form={EXPORT_FORM} names={WINDOW_NAMES} />
        <FieldProblems problems={problems} form={EXPORT_FORM} names="data_set" />
        <Line>{`Days are in UTC, and the last day is included. One export carries at most ${String(page.max_entries)} entries.`}</Line>
        <div>
          <Button type="submit" disabled={busy} className="min-h-11 sm:min-h-9">
            <Download aria-hidden /> {EXPORT_LABEL}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={confirming && span !== null}
        question={`Export the audit trail from ${firstDay} to ${lastDay}, for ${reasonLabel(reason)}?`}
        consequence={`${page.export_told} ${page.document_told}`}
        confirmLabel={EXPORT_LABEL}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={take}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </>
  );
}

function Transfer({ page, onTaken }: { readonly page: DataTransferBody; readonly onTaken: (sentence: string) => void }) {
  return (
    <>
      <SectionCard
        title={EXPORT_LABEL}
        lede={page.export_told}
        footer={
          <>
            {page.form_told ? <Line>{page.form_told}</Line> : null}
            <Line>{page.document_told}</Line>
          </>
        }
      >
        {page.exportable ? <ExportForm page={page} onTaken={onTaken} /> : <Note>{NOT_EXPORTABLE}</Note>}
      </SectionCard>
      <WholeList
        title="Your exports"
        caption="Your exports"
        columns={EXPORT_COLUMNS}
        rows={page.exports}
        rowId={(row) => row.export_id}
        rowLabel={(row) => at(row.produced_at)}
        empty={NO_EXPORTS}
        emptyDescription={NO_EXPORTS_MORE}
        footer={<Line>{page.own_exports_told}</Line>}
      />
      <WholeList
        title={CATALOGUE_HEADING}
        caption={CATALOGUE_HEADING}
        columns={CATALOGUE_COLUMNS}
        rows={page.catalogue}
        rowId={(row) => `${row.direction}:${row.key}`}
        rowLabel={(row) => row.label}
        empty={NOTHING_TO_MOVE}
      />
    </>
  );
}

export function DataTransferPage() {
  // A counter rather than a boolean, so each export reads the list again. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [taken, setTaken] = useState<string | null>(null);
  const onTaken = useCallback((sentence: string) => {
    setTaken(sentence);
    setGeneration((current) => current + 1);
  }, []);
  const answer = useResource<unknown>(DATA_TRANSFER_API_PATH, generation);
  const body = answer.data === null ? null : readDataTransfer(answer.data);

  return (
    <OpsPage
      crumbs={[{ label: GOVERNANCE }, { label: DATA_TRANSFER_HEADING }]}
      title={DATA_TRANSFER_HEADING}
      lede={DATA_TRANSFER_LEDE}
      primary={
        <UnavailableAction
          label={UNAVAILABLE.importData.label}
          text={UNAVAILABLE.importData.label}
          icon={<Upload aria-hidden />}
          reason={UNAVAILABLE.importData.reason}
        />
      }
      notice={
        taken === null ? null : (
          <div role="status">
            <Note>{taken}</Note>
          </div>
        )
      }
      loading={READING_DATA_TRANSFER}
      busy={answer.busy && answer.data === null}
      failure={answer.failure}
      body={body}
    >
      {(page) => <Transfer page={page} onTaken={onTaken} />}
    </OpsPage>
  );
}
