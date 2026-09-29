/**
 * The Rate limits screen's changes: every budget and request window a person may set, what is in
 * force, the product's figure and the bounds, and a figure set from its row (M22.4.1, M22.1.2).
 *
 * A figure is set from its row, checked against the knob's own bounds before anything is sent, and
 * confirmed with a sentence saying what it becomes and when every part of the install uses it,
 * because a window or a budget changes what everybody is admitted to from the next request. The
 * controls are drawn only for a reader the answer says may change them; the API refuses without
 * the authority whatever this card drew.
 *
 * Task ids: M22.4.1, M22.1.2
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, LoadingState, SectionCard, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { FailureNotice } from "../../ui/FailureNotice";
import {
  CHANGE_LIMIT,
  KEEP_LIMIT,
  NOT_READ,
  READING_TUNING,
  SAVE_LIMIT,
  TUNING_API_PATH,
  TUNING_HEADING,
  TUNING_LEDE,
  boundsWords,
  changeConsequence,
  changedSentence,
  figureProblem,
  figureWords,
  readTuning,
  sourceWords,
  tunePath,
  type Knob,
} from "../tuningQuery";
import { Line, WholeList } from "./parts";

const COLUMNS: readonly EntityColumn<Knob>[] = [
  { id: "label", header: "Limit", hideable: false, cell: (row) => row.label, text: (row) => row.label },
  {
    id: "value",
    header: "In force",
    align: "end",
    cell: (row) => figureWords(row.value, row.unit),
    text: (row) => figureWords(row.value, row.unit),
  },
  { id: "source", header: "Set by", cell: (row) => sourceWords(row), text: (row) => sourceWords(row) },
  {
    id: "default",
    header: "Product's figure",
    hidden: true,
    align: "end",
    cell: (row) => row.default.toLocaleString("en-GB"),
    text: (row) => String(row.default),
  },
  { id: "bounds", header: "Can be set", cell: (row) => boundsWords(row), text: (row) => boundsWords(row) },
  { id: "because", header: "Why those bounds", hidden: true, cell: (row) => row.bounds_because, text: (row) => row.bounds_because },
];

export function LimitSettings() {
  const answer = useResource<unknown>(TUNING_API_PATH);
  const [written, setWritten] = useState<unknown>(null);
  const [editing, setEditing] = useState<Knob | null>(null);
  const [typed, setTyped] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [asked, setAsked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);

  const data = written !== null ? written : answer.data;
  const body = data === null ? null : readTuning(data);

  if (answer.busy && written === null) {
    return (
      <SectionCard title={TUNING_HEADING}>
        <LoadingState label={READING_TUNING} rows={3} />
      </SectionCard>
    );
  }
  if (answer.failure !== null && written === null) {
    return (
      <SectionCard title={TUNING_HEADING}>
        <FailureNotice failure={answer.failure} />
      </SectionCard>
    );
  }
  if (body === null) {
    return (
      <SectionCard title={TUNING_HEADING}>
        <Line>{NOT_READ}</Line>
      </SectionCard>
    );
  }

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (editing === null) {
      return;
    }
    setFailure(null);
    const found = figureProblem(editing, typed);
    setProblem(found);
    setAsked(found === null);
  };

  const send = (knob: Knob) => {
    const amount = Number(typed.trim());
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(tunePath(knob.name), {
        method: "PUT",
        body: { value: amount },
      });
      setBusy(false);
      setAsked(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setEditing(null);
      setWritten(result.data);
      setTold(changedSentence(knob, amount));
    })();
  };

  const field = "limit-settings-figure";
  return (
    <>
      <WholeList
        title={TUNING_HEADING}
        lede={`${TUNING_LEDE} ${body.in_force}`}
        caption={TUNING_HEADING}
        columns={COLUMNS}
        rows={body.knobs}
        rowId={(row) => row.name}
        rowLabel={(row) => row.label}
        rowActions={
          body.may_change
            ? (row) => (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  aria-label={`${CHANGE_LIMIT}: ${row.label}`}
                  onClick={() => {
                    setEditing(row);
                    setTyped(String(row.value));
                    setProblem(null);
                    setFailure(null);
                    setTold(null);
                    setAsked(false);
                  }}
                >
                  {CHANGE_LIMIT}
                </Button>
              )
            : undefined
        }
        exportName="changeable-limits"
        empty={NOT_READ}
      />
      {editing === null ? null : (
        <SectionCard title={editing.label} lede={editing.bounds_because}>
          <form className="grid gap-3" aria-label={editing.label} onSubmit={ask}>
            <label className="text-sm font-medium text-ink" htmlFor={field}>
              {`${editing.label}, ${boundsWords(editing)} ${editing.unit}`}
            </label>
            <Input
              id={field}
              type="text"
              inputMode="numeric"
              name="value"
              value={typed}
              aria-invalid={problem !== null}
              aria-describedby={problem === null ? undefined : `${field}-problem`}
              onChange={(event) => {
                setTyped(event.target.value);
              }}
            />
            {problem === null ? null : (
              <p id={`${field}-problem`} className="m-0 text-sm text-danger" role="alert">
                {problem}
              </p>
            )}
            <div>
              <Button type="submit" disabled={busy} className="min-h-11 sm:min-h-9">
                {SAVE_LIMIT}
              </Button>
            </div>
          </form>
          <ConfirmDialog
            open={asked}
            question={`Change ${editing.label.toLowerCase()}?`}
            consequence={changeConsequence(editing, Number(typed.trim()), body.in_force)}
            confirmLabel={SAVE_LIMIT}
            cancelLabel={KEEP_LIMIT}
            busy={busy}
            onConfirm={() => {
              send(editing);
            }}
            onCancel={() => {
              setAsked(false);
            }}
          />
        </SectionCard>
      )}
      {told === null ? null : (
        <p className="m-0 text-sm text-ink" role="status">
          {told}
        </p>
      )}
      {failure === null ? null : <FailureNotice failure={failure} />}
    </>
  );
}
