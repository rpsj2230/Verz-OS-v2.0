/**
 * The golden questions every change to the failover matrix is asked before it is used: the list,
 * each with the person it is asked as by name, retiring one, and adding one.
 *
 * **A person is chosen by name** from `GET /routing/golden-questions/askers`, which lists the live
 * people the directory holds to the matrix writer who may record a question as any of them; the id
 * the API stores is sent and never drawn (`brain.routing_routes.A_PERSON_IS_CHOSEN_BY_NAME`).
 *
 * **Adding and retiring are confirmed**, because each changes what every later change must pass.
 *
 * Task ids: M5.6.2, M27.16.1
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { useResource, type Resource } from "../../api/useResource";
import { ConfirmDialog, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { problemAttributes } from "../../ui/FieldProblems";
import {
  ADD_GOLDEN,
  addGoldenConsequence,
  addGoldenQuestion,
  ASKED_AS_LABEL,
  askedAsWords,
  ASKERS_API_PATH,
  blankGoldenProblems,
  CHOOSE_A_PERSON,
  expectWords,
  GOLDEN_API_PATH,
  GOLDEN_HEADING,
  GOLDEN_LEDE,
  KEEP_GOLDEN,
  MORE_PEOPLE,
  NOBODY_LISTED,
  NO_GOLDEN,
  readAskers,
  readGolden,
  RETIRE_GOLDEN,
  RETIRE_GOLDEN_CONSEQUENCE,
  retireGoldenApiPath,
  retireGoldenQuestion,
  type GoldenAsked,
  type GoldenRow,
} from "../matrixGateQuery";
import { FIELD_CONTROL, FormField } from "./FormField";
import { StepsToPass } from "./HeldChange";

const FORM = "golden";

/** The question's field, which the Routing page's "Add a golden question" takes the reader to. */
export const GOLDEN_QUESTION_FIELD = `${FORM}-question`;

export const LOADING_GOLDEN = "Loading the golden questions.";
export const QUESTION_HINT = "The question as a person would ask it, up to 2000 characters.";
export const ASKED_AS_HINT = "The person it is asked as. It is answered only from what they may read.";
export const EXPECT_HINT = "Whether a change must still answer it, or must still refuse it.";

type Pending =
  | { readonly kind: "add"; readonly asked: GoldenAsked; readonly name: string }
  | { readonly kind: "retire"; readonly row: GoldenRow };

export function GoldenQuestions({
  golden,
  version,
  onChanged,
}: {
  /** The golden questions, read once by the page for this card and the held change above it. */
  readonly golden: Resource<unknown>;
  readonly version: number;
  readonly onChanged: () => void;
}) {
  const askers = useResource<unknown>(ASKERS_API_PATH, version);
  const [question, setQuestion] = useState("");
  const [askedAs, setAskedAs] = useState("");
  const [expect, setExpect] = useState<GoldenAsked["expect"]>("answer");
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const problems = [...blank, ...(failure?.problems ?? [])];
  const rows = golden.data === null ? [] : readGolden(golden.data);
  const people = askers.data === null ? [] : readAskers(askers.data);
  const cut =
    typeof askers.data === "object" && askers.data !== null && (askers.data as { truncated?: unknown }).truncated === true;
  const id = (name: string) => `${FORM}-${name}`;

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankGoldenProblems(question, askedAs);
    setBlank(found);
    if (found.length > 0) {
      return;
    }
    const chosen = people.find((one) => one.id === askedAs);
    setPending({ kind: "add", asked: { question: question.trim(), asked_as: askedAs.trim(), expect }, name: chosen?.name ?? askedAs.trim() });
  };

  const send = (asked: Pending) => {
    setBusy(true);
    void (async () => {
      const result =
        asked.kind === "add"
          ? await request<unknown>(GOLDEN_API_PATH, { method: "POST", body: asked.asked })
          : await request<unknown>(retireGoldenApiPath(asked.row.id), { method: "POST" });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      if (asked.kind === "add") {
        setQuestion("");
        setAskedAs("");
      }
      onChanged();
    })();
  };

  return (
    <SectionCard title={GOLDEN_HEADING} lede={GOLDEN_LEDE}>
      <div className="flex flex-col gap-4">
        {golden.failure !== null ? (
          <FailureState failure={golden.failure} />
        ) : golden.busy ? (
          <LoadingState label={LOADING_GOLDEN} rows={2} />
        ) : rows.length === 0 ? (
          <div className="flex flex-col gap-2">
            <Note kind="not-yet">{NO_GOLDEN}</Note>
            <StepsToPass />
          </div>
        ) : (
          <Table className="text-[13px]">
            <TableCaption className="sr-only">{GOLDEN_HEADING}</TableCaption>
            <TableHeader className="bg-sunk">
              <TableRow className="hover:bg-transparent">
                <TableHead scope="col">Question</TableHead>
                <TableHead scope="col">{ASKED_AS_LABEL}</TableHead>
                <TableHead scope="col">Expected</TableHead>
                <TableHead scope="col">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="[overflow-wrap:anywhere] whitespace-normal">{row.question}</TableCell>
                  <TableCell className="[overflow-wrap:anywhere] whitespace-normal">{askedAsWords(row)}</TableCell>
                  <TableCell>{expectWords(row.expect)}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      className="min-h-11 sm:min-h-8"
                      disabled={busy}
                      aria-label={`${RETIRE_GOLDEN}: ${row.question}`}
                      onClick={() => {
                        setFailure(null);
                        setPending({ kind: "retire", row });
                      }}
                    >
                      {RETIRE_GOLDEN}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <form aria-label="Add a golden question" className="flex flex-col gap-3 border-t border-line pt-3" onSubmit={ask} noValidate>
          <FormField id={id("question")} label="Question" hint={QUESTION_HINT} form={FORM} name="question" problems={problems}>
            <input
              id={id("question")}
              name="question"
              className={FIELD_CONTROL}
              value={question}
              maxLength={2000}
              {...problemAttributes(problems, FORM, "question", `${id("question")}-hint`)}
              onChange={(event) => {
                setQuestion(event.target.value);
              }}
            />
          </FormField>
          <div className="[display:grid] grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField id={id("asked_as")} label={ASKED_AS_LABEL} hint={ASKED_AS_HINT} form={FORM} name="asked_as" problems={problems}>
              <select
                id={id("asked_as")}
                name="asked_as"
                className={FIELD_CONTROL}
                value={askedAs}
                {...problemAttributes(problems, FORM, "asked_as", `${id("asked_as")}-hint`)}
                onChange={(event) => {
                  setAskedAs(event.target.value);
                }}
              >
                <option value="">{CHOOSE_A_PERSON}</option>
                {people.map((one) => (
                  <option key={one.id} value={one.id}>
                    {one.name}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField id={id("expect")} label="It must be" hint={EXPECT_HINT} form={FORM} name="expect" problems={problems}>
              <select
                id={id("expect")}
                name="expect"
                className={FIELD_CONTROL}
                value={expect}
                onChange={(event) => {
                  setExpect(event.target.value === "refuse" ? "refuse" : "answer");
                }}
              >
                <option value="answer">answered</option>
                <option value="refuse">refused</option>
              </select>
            </FormField>
          </div>
          {askers.failure !== null ? <FailureState failure={askers.failure} /> : null}
          {!askers.busy && askers.failure === null && people.length === 0 ? <Note>{NOBODY_LISTED}</Note> : null}
          {cut ? <Note>{MORE_PEOPLE}</Note> : null}
          {failure === null || failure.problems.length > 0 ? null : <FailureState failure={failure} />}
          <div className="flex justify-end">
            <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
              {ADD_GOLDEN}
            </Button>
          </div>
        </form>
      </div>
      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "" : pending.kind === "add" ? addGoldenQuestion(pending.name) : retireGoldenQuestion(pending.row)}
        consequence={
          pending === null ? "" : pending.kind === "add" ? addGoldenConsequence(pending.asked, pending.name) : RETIRE_GOLDEN_CONSEQUENCE
        }
        confirmLabel={pending?.kind === "retire" ? RETIRE_GOLDEN : ADD_GOLDEN}
        cancelLabel={KEEP_GOLDEN}
        busy={busy}
        onConfirm={() => {
          if (pending !== null) {
            send(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </SectionCard>
  );
}
