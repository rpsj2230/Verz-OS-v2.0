/**
 * Import and export: what data this install can bring in or take out, whether each can run today
 * and why not when it cannot, and the one export that runs, taken as a confirmed write.
 *
 * `docs/screens.html` does not draw this screen. The owner's standard lists import and export, so
 * the screen takes the design's general shape and lists every data set the code knows how to move,
 * with the API's sentence beside each one that cannot move yet, rather than a row of buttons that
 * reach nothing.
 *
 * **Taking an export is confirmed, and the confirmation says what an export is.** The question
 * names the data set and the days; the consequence is the API's two sentences about a copy that
 * leaves every guard behind and a document handed over once. The document is saved as a file when
 * the answer arrives and is never drawn on the screen.
 *
 * **Nothing here decides who may export.** `exportable` only decides whether the form is drawn, and
 * the route decides again, asking before it reads anything.
 *
 * Task ids: M27.8.16
 */

import { useCallback, useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
import {
  CANNOT_SAVE,
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
} from "./dataTransferQuery";
import { problemsFor, readProblems, when, type Problem } from "./webhooksQuery";

export const DATA_TRANSFER_HEADING = "Import and export";
export const DATA_TRANSFER_CRUMB = "Govern › Import and export";
export const DATA_TRANSFER_LEDE =
  "What this install can bring in and take out, whether each can be done today, and the exports " +
  "you have taken. An export is recorded in the audit trail under your name.";

export const READING_DATA_TRANSFER = "Reading what can be imported and exported.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const NOT_EXPORTABLE =
  "Taking an export needs the export grant and the grant to read the whole audit trail, both over " +
  "the whole company. You do not hold both, so no export can be taken here.";
export const NO_EXPORTS = "You have not taken an export.";
export const EXPORT_LABEL = "Export the audit trail";
export const KEEP_LABEL = "Change nothing";
export const NOT_A_WINDOW = "Choose a first and a last day.";

function Failure({ failure }: { readonly failure: ApiFailure }) {
  return (
    <Notice
      title={failure.status === 0 ? THE_BRAIN_COULD_NOT_BE_REACHED : SOMETHING_DID_NOT_WORK}
      traceId={failure.traceId}
    >
      <p>{failure.message}</p>
    </Notice>
  );
}

function Catalogue({ title, rows }: { readonly title: string; readonly rows: readonly DataSetRow[] }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      <div className="grid__scroll">
        <table className="grid__table" aria-label={title}>
          <thead>
            <tr>
              <th scope="col">Data</th>
              <th scope="col">What it carries</th>
              <th scope="col">Today</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td>{row.label}</td>
                <td>{row.carries}</td>
                <td>
                  {row.runs ? <strong>Available. </strong> : null}
                  {row.told}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FieldProblems({ problems, field }: { readonly problems: readonly Problem[]; readonly field: string }) {
  const found = problemsFor(problems, field);
  if (found.length === 0) {
    return null;
  }
  return (
    <ul className="field-description" aria-label={`Problems with ${field}`}>
      {found.map((one) => (
        <li key={one}>{one}</li>
      ))}
    </ul>
  );
}

function TransferPage({
  page,
  onTaken,
}: {
  readonly page: DataTransferBody;
  readonly onTaken: (sentence: string) => void;
}) {
  const [reason, setReason] = useState<string>(page.reasons[0] ?? "");
  const [reference, setReference] = useState("");
  const [firstDay, setFirstDay] = useState("");
  const [lastDay, setLastDay] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

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
        const found = result.failure.status === 422 ? readProblems(result.body) : null;
        setProblems(found ?? []);
        setFailure(found === null ? result.failure : null);
        return;
      }
      setProblems([]);
      setFailure(null);
      const taken = readTaken(result.data);
      if (taken === null) {
        onTaken(SOMETHING_DID_NOT_WORK);
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
      setProblems([{ field: "window", code: "no_window", message: NOT_A_WINDOW }]);
      return;
    }
    setConfirming(true);
  }

  const exports = page.catalogue.filter((row) => row.direction === "export");
  const imports = page.catalogue.filter((row) => row.direction === "import");

  return (
    <>
      <Catalogue title="Export" rows={exports} />
      <Catalogue title="Import" rows={imports} />

      <section className="card">
        <h2>{EXPORT_LABEL}</h2>
        <p>{page.export_told}</p>
        <p className="note">{page.document_told}</p>
        {failure === null ? null : <Failure failure={failure} />}
        {!page.exportable ? (
          <p className="note">{NOT_EXPORTABLE}</p>
        ) : confirming && span !== null ? (
          <ConfirmAction
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
        ) : (
          <form className="form" aria-label={EXPORT_LABEL} onSubmit={ask}>
            <label className="control-label">
              Reason{" "}
              <select
                className="form-control"
                value={reason}
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
            </label>
            <FieldProblems problems={problems} field="reason" />
            <label className="control-label">
              Reference of the written request{" "}
              <input
                className="form-control"
                type="text"
                value={reference}
                onChange={(event) => {
                  setReference(event.target.value);
                }}
              />
            </label>
            <p className="field-description">A ticket or matter number. Never a person&apos;s name.</p>
            <FieldProblems problems={problems} field="reason_reference" />
            <label className="control-label">
              First day{" "}
              <input
                className="form-control"
                type="date"
                value={firstDay}
                onChange={(event) => {
                  setFirstDay(event.target.value);
                }}
              />
            </label>
            <label className="control-label">
              Last day{" "}
              <input
                className="form-control"
                type="date"
                value={lastDay}
                onChange={(event) => {
                  setLastDay(event.target.value);
                }}
              />
            </label>
            <FieldProblems problems={problems} field="window" />
            <FieldProblems problems={problems} field="data_set" />
            <p className="field-description">
              Days are in UTC, and the last day is included. One export carries at most{" "}
              {page.max_entries} entries.
            </p>
            <div className="form-actions">
              <button type="submit" className="button" disabled={busy}>
                {EXPORT_LABEL}
              </button>
            </div>
          </form>
        )}
      </section>

      <section className="card">
        <h2>Your exports</h2>
        {page.exports.length === 0 ? (
          <p className="note">{NO_EXPORTS}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table" aria-label="Your exports">
              <thead>
                <tr>
                  <th scope="col">Taken</th>
                  <th scope="col">Reason</th>
                  <th scope="col">Reference</th>
                  <th scope="col">Window</th>
                  <th scope="col">Chain</th>
                  <th scope="col">File digest</th>
                </tr>
              </thead>
              <tbody>
                {page.exports.map((row) => (
                  <tr key={row.export_id}>
                    <td>{when(row.produced_at)}</td>
                    <td>{reasonLabel(row.reason)}</td>
                    <td>
                      <code>{row.reason_reference}</code>
                    </td>
                    <td>{windowSentence(row)}</td>
                    <td>{row.verified ? "Verified" : "Broken; the document says where"}</td>
                    <td>
                      <code>{row.document_digest}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="note">{page.own_exports_told}</p>
      </section>
    </>
  );
}

function TransferBody({ onTaken }: { readonly onTaken: (sentence: string) => void }) {
  const answer = useResource<unknown>(DATA_TRANSFER_API_PATH);
  if (answer.failure) {
    return <Failure failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_DATA_TRANSFER}
      </p>
    );
  }
  const page = readDataTransfer(answer.data);
  if (page === null) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK}>
        <p>The answer about import and export was not in a shape this screen can read.</p>
      </Notice>
    );
  }
  return <TransferPage page={page} onTaken={onTaken} />;
}

export function DataTransfer() {
  // A counter rather than a boolean, so each export reads the list again. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [taken, setTaken] = useState<string | null>(null);
  const onTaken = useCallback((sentence: string) => {
    setTaken(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{DATA_TRANSFER_CRUMB}</p>
      <h1>{DATA_TRANSFER_HEADING}</h1>
      <p className="lede">{DATA_TRANSFER_LEDE}</p>
      {taken === null ? null : (
        <p className="note" role="status">
          {taken}
        </p>
      )}
      <TransferBody key={generation} onTaken={onTaken} />
    </article>
  );
}
