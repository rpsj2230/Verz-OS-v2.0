/**
 * The Models screen's prices: what a million tokens cost on each model, and whether its calls are
 * costed (M27.12.5).
 *
 * Every model a step on the failover matrix names is listed, with any model priced and no longer in
 * use, so an administrator sees at a glance which calls leave no cost. A price is set from its row,
 * checked for blanks before anything is sent, and confirmed with a sentence saying which calls it
 * costs from when, because it decides every department's cost figures from the next call. The
 * controls are drawn only for a reader the providers answer says may switch a provider, which is
 * the capability the API asks; the API refuses without it whatever this card drew.
 *
 * While the install has no currency the card says where to choose one and offers no control: the
 * API refuses a price in no currency (`brain.provider_routes.A_PRICE_NEEDS_THE_INSTALLS_CURRENCY`).
 *
 * Task ids: M27.12.5
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure, FieldProblem } from "../api/errors";
import { useResource } from "../api/useResource";
import {
  CHOOSE_A_CURRENCY_FIRST,
  INPUT_LABEL,
  KEEP_PRICE,
  NO_MODELS,
  NOT_IN_USE,
  OUTPUT_LABEL,
  PRICES_API_PATH,
  PRICES_HEADING,
  SAVE_PRICE,
  SET_PRICE,
  costedWords,
  majorFromMinor,
  modelWords,
  priceBody,
  priceProblems,
  priceWords,
  pricedSentence,
  pricesLede,
  readPrices,
  type ModelPriceRow,
} from "../pages/modelPricesQuery";
import { UNSET_CURRENCY } from "../pages/spendQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import { ConfirmAction } from "./ConfirmAction";
import type { GridColumn } from "./gridFeatures";
import { GridTable } from "./kit/GridTable";

const PRICE_FORM = "model-price";

export function ModelPrices({ editable }: { readonly editable: boolean }) {
  const answer = useResource<unknown>(PRICES_API_PATH);
  const [written, setWritten] = useState<unknown>(null);
  const [editing, setEditing] = useState<ModelPriceRow | null>(null);
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [asked, setAsked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);

  const data = written !== null ? written : answer.data;
  const body = data === null ? null : readPrices(data);
  const problems = [...blank, ...(failure?.problems ?? [])];
  const field = (name: string) => `model-price-${name}`;

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = priceProblems(input, output);
    setBlank(found);
    if (found.length === 0) {
      setAsked(true);
    }
  };

  const send = (row: ModelPriceRow) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(PRICES_API_PATH, {
        method: "PUT",
        body: priceBody(row, input, output),
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
      setTold(pricedSentence(row));
    })();
  };

  if (answer.busy && written === null) {
    return (
      <section className="card" aria-labelledby="models-prices">
        <h2 id="models-prices">{PRICES_HEADING}</h2>
        <p className="note" role="status">
          Loading the prices.
        </p>
      </section>
    );
  }
  if (answer.failure !== null && written === null) {
    return (
      <section className="card" aria-labelledby="models-prices">
        <h2 id="models-prices">{PRICES_HEADING}</h2>
        <FailureNotice failure={answer.failure} />
      </section>
    );
  }
  if (body === null) {
    return (
      <section className="card" aria-labelledby="models-prices">
        <h2 id="models-prices">{PRICES_HEADING}</h2>
        <p className="note">The prices could not be read.</p>
      </section>
    );
  }

  const unset = body.currency === UNSET_CURRENCY;
  const controls = editable && !unset;

  const columns: GridColumn<ModelPriceRow>[] = [
    {
      id: "model",
      header: "Model",
      cell: ({ row }) => (
        <>
          {modelWords(row.original)}
          {row.original.on_ladder ? null : <span className="note"> ({NOT_IN_USE})</span>}
        </>
      ),
    },
    { id: "input", header: INPUT_LABEL, cell: ({ row }) => priceWords(row.original.input_minor_per_million) },
    { id: "output", header: OUTPUT_LABEL, cell: ({ row }) => priceWords(row.original.output_minor_per_million) },
    { id: "costed", header: "Costed", cell: ({ row }) => costedWords(row.original, body.currency) },
  ];
  if (controls) {
    columns.push({
      id: "actions",
      header: "Actions",
      cell: ({ row }) => {
        const one = row.original;
        return (
          <button
            type="button"
            className="button"
            disabled={busy}
            aria-label={`${SET_PRICE}: ${modelWords(one)}`}
            onClick={() => {
              setEditing(one);
              setInput(one.costed && one.input_minor_per_million !== null ? majorFromMinor(one.input_minor_per_million) : "");
              setOutput(one.costed && one.output_minor_per_million !== null ? majorFromMinor(one.output_minor_per_million) : "");
              setBlank([]);
              setFailure(null);
              setTold(null);
              setAsked(false);
            }}
          >
            {SET_PRICE}
          </button>
        );
      },
    });
  }

  return (
    <section className="card" aria-labelledby="models-prices">
      <h2 id="models-prices">{PRICES_HEADING}</h2>
      <p className="note">{pricesLede(body.currency)}</p>
      {unset && editable ? <p className="note">{CHOOSE_A_CURRENCY_FIRST}</p> : null}
      {body.models.length === 0 ? (
        <p className="note">{NO_MODELS}</p>
      ) : (
        <GridTable
          look="grid"
          caption="What a million tokens cost on each model"
          columns={columns}
          rows={body.models}
          rowId={(row) => `${row.provider}/${row.model}`}
        />
      )}
      {editing === null ? null : (
        <form className="form" aria-label={`Price of ${modelWords(editing)}`} onSubmit={ask}>
          <h3>Price of {modelWords(editing)}</h3>
          <label className="control-label" htmlFor={field("input")}>
            {INPUT_LABEL}, in {body.currency}
          </label>
          <input
            id={field("input")}
            className="form-control"
            inputMode="decimal"
            name="input_minor_per_million"
            value={input}
            {...problemAttributes(problems, PRICE_FORM, "input_minor_per_million")}
            onChange={(event) => {
              setInput(event.target.value);
            }}
          />
          <FieldProblems problems={problems} form={PRICE_FORM} names="input_minor_per_million" />
          <label className="control-label" htmlFor={field("output")}>
            {OUTPUT_LABEL}, in {body.currency}
          </label>
          <input
            id={field("output")}
            className="form-control"
            inputMode="decimal"
            name="output_minor_per_million"
            value={output}
            {...problemAttributes(problems, PRICE_FORM, "output_minor_per_million")}
            onChange={(event) => {
              setOutput(event.target.value);
            }}
          />
          <FieldProblems problems={problems} form={PRICE_FORM} names="output_minor_per_million" />
          <p>
            <button type="submit" className="button" disabled={busy || asked}>
              {SAVE_PRICE}
            </button>
          </p>
        </form>
      )}
      {editing === null || !asked ? null : (
        <ConfirmAction
          question={`Price ${modelWords(editing)}?`}
          consequence={
            `Every call to ${modelWords(editing)} from now on is costed at ${body.currency} ${input.trim()} ` +
            `per million tokens sent and ${body.currency} ${output.trim()} per million received. Calls ` +
            "already recorded keep the cost they were recorded at."
          }
          confirmLabel={SAVE_PRICE}
          cancelLabel={KEEP_PRICE}
          busy={busy}
          onConfirm={() => {
            send(editing);
          }}
          onCancel={() => {
            setAsked(false);
          }}
        />
      )}
      {told === null ? null : (
        <p className="note" role="status">
          {told}
        </p>
      )}
      {failure === null ? null : <FailureNotice failure={failure} />}
    </section>
  );
}
