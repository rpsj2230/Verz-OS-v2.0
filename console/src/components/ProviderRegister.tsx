/**
 * The Models screen's provider register: each provider's terms and what it has been sent, the
 * terms recorded, an OpenAI-compatible provider added with its key, and the register downloaded.
 *
 * `providerRegisterQuery.ts` holds the arguments. It reads nothing of its own: it is handed the
 * providers answer the health card holds, so the register and the chain are one plan and one
 * request, and every write answers with the plan after it, which it hands back to the card. Every
 * write asks first through `components/ConfirmAction.tsx`, and every write is refused by the API
 * without the authority it needs whatever this page drew: the matrix write over everything for terms and retiring, and that
 * and the credential authority for adding.
 *
 * Task ids: M5.6.4, M5.7.2, M5.1.3, M5.5.3
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure, FieldProblem } from "../api/errors";
import { ConfirmAction } from "./ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import { CANNOT_SAVE, saveDocument } from "../pages/dataTransferQuery";
import {
  ADD_CONSEQUENCE,
  ADD_PROVIDER,
  ADD_PROVIDER_API_PATH,
  ADD_PROVIDER_HEADING,
  ADD_PROVIDER_NOTE,
  addQuestion,
  blankAddProblems,
  blankTermsProblems,
  DO_NOT_ADD,
  DOWNLOAD_REGISTER,
  KEEP_PROVIDER,
  KEEP_TERMS,
  laneOverrides,
  modelNames,
  NOT_RECORDED,
  NOTHING_SENT,
  readRegister,
  readRegisterDocument,
  RECORD_TERMS,
  REGISTER_API_PATH,
  REGISTER_HEADING,
  REGISTER_LEDE,
  REGISTER_SAVED,
  RESIDENCY_CLASSES,
  RETIRE_CONSEQUENCE,
  RETIRE_PROVIDER,
  retireProviderApiPath,
  retireQuestion,
  SAVE_TERMS,
  termsApiPath,
  termsConsequence,
  termsQuestion,
  type AddAsked,
  type RegisterRow,
  type TermsAsked,
} from "../pages/providerRegisterQuery";

const TERMS_FORM = "terms";
const ADD_FORM = "add-provider";

type Pending =
  | { readonly kind: "terms"; readonly provider: string; readonly asked: TermsAsked }
  | { readonly kind: "retire"; readonly provider: string }
  | { readonly kind: "add"; readonly asked: AddAsked };

function Terms({ row }: { readonly row: RegisterRow }) {
  const terms = row.registered;
  if (terms === null) {
    return <p className="note">{NOT_RECORDED}</p>;
  }
  return (
    <dl className="fields">
      {terms.base_url === null ? null : (
        <div className="fields__row">
          <dt>Address</dt>
          <dd>
            <code>{terms.base_url}</code>
          </dd>
        </div>
      )}
      <div className="fields__row">
        <dt>Region</dt>
        <dd>
          {terms.processing_region} ({terms.residency_class.replace("_", " ")})
        </dd>
      </div>
      <div className="fields__row">
        <dt>Stored</dt>
        <dd>{terms.storage_location === "" ? NOT_RECORDED : terms.storage_location}</dd>
      </div>
      <div className="fields__row">
        <dt>Retention</dt>
        <dd>{terms.retention_terms === "" ? NOT_RECORDED : terms.retention_terms}</dd>
      </div>
      <div className="fields__row">
        <dt>Training</dt>
        <dd>{terms.training_terms === "" ? NOT_RECORDED : terms.training_terms}</dd>
      </div>
      <div className="fields__row">
        <dt>Agreement</dt>
        <dd>
          {terms.agreement_url === null ? (
            NOT_RECORDED
          ) : (
            <a href={terms.agreement_url} rel="noreferrer noopener" target="_blank">
              {terms.agreement_url}
            </a>
          )}
        </dd>
      </div>
      {terms.lane_overrides.map((one) => (
        <div className="fields__row" key={one.lane}>
          <dt>{one.lane} lane</dt>
          <dd>
            {one.timeout_seconds === null ? "" : `${String(one.timeout_seconds)} s timeout `}
            {one.attempts === null ? "" : `${String(one.attempts)} attempts`}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ProviderRegister({
  data,
  onWritten,
}: {
  /** The providers answer the health card drew, as the API sent it. */
  readonly data: unknown;
  /** Called with the plan a write answered with, which the card draws from then on. */
  readonly onWritten: (plan: unknown) => void;
}) {
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [said, setSaid] = useState<string | null>(null);

  const [editing, setEditing] = useState<string | null>(null);
  const [region, setRegion] = useState("");
  const [residency, setResidency] = useState<TermsAsked["residency_class"]>("global");
  const [storage, setStorage] = useState("");
  const [retention, setRetention] = useState("");
  const [training, setTraining] = useState("");
  const [agreement, setAgreement] = useState("");
  const [laneTimeout, setLaneTimeout] = useState("");
  const [laneAttempts, setLaneAttempts] = useState("");
  const [termsBlank, setTermsBlank] = useState<FieldProblem[]>([]);

  const [slug, setSlug] = useState("");
  const [label, setLabel] = useState("");
  const [address, setAddress] = useState("");
  const [models, setModels] = useState("");
  const [key, setKey] = useState("");
  const [addBlank, setAddBlank] = useState<FieldProblem[]>([]);

  const termsProblems = [...termsBlank, ...(failure?.problems ?? [])];
  const addProblems = [...addBlank, ...(failure?.problems ?? [])];
  const body = readRegister(data);

  const send = (asked: Pending) => {
    setBusy(true);
    void (async () => {
      const result =
        asked.kind === "terms"
          ? await request<unknown>(termsApiPath(asked.provider), { method: "PUT", body: asked.asked })
          : asked.kind === "retire"
            ? await request<unknown>(retireProviderApiPath(asked.provider), { method: "POST" })
            : await request<unknown>(ADD_PROVIDER_API_PATH, { method: "POST", body: asked.asked });
      setBusy(false);
      setPending(null);
      // The key leaves the page's state whatever the answer, so it is held no longer than the request.
      setKey("");
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      if (asked.kind === "add") {
        setSlug("");
        setLabel("");
        setAddress("");
        setModels("");
      }
      setEditing(null);
      onWritten(result.data);
    })();
  };

  const download = () => {
    void (async () => {
      const result = await request<unknown>(REGISTER_API_PATH);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const document = readRegisterDocument(result.data);
      if (document === null) {
        return;
      }
      setSaid(saveDocument(document.filename, document.document, window.document) ? REGISTER_SAVED : CANNOT_SAVE);
    })();
  };

  const openTerms = (row: RegisterRow) => {
    const terms = row.registered;
    setEditing(row.provider);
    setRegion(terms?.processing_region ?? "global");
    setResidency(
      terms?.residency_class === "region_pinned" || terms?.residency_class === "on_prem" ? terms.residency_class : "global",
    );
    setStorage(terms?.storage_location ?? "");
    setRetention(terms?.retention_terms ?? "");
    setTraining(terms?.training_terms ?? "");
    setAgreement(terms?.agreement_url ?? "");
    const answerLane = terms?.lane_overrides.find((one) => one.lane === "answer");
    setLaneTimeout(answerLane?.timeout_seconds === null || answerLane === undefined ? "" : String(answerLane.timeout_seconds));
    setLaneAttempts(answerLane?.attempts === null || answerLane === undefined ? "" : String(answerLane.attempts));
    setTermsBlank([]);
    setFailure(null);
  };

  const askTerms = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (editing === null) {
      return;
    }
    setFailure(null);
    const found = blankTermsProblems(region);
    setTermsBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({
      kind: "terms",
      provider: editing,
      asked: {
        processing_region: region.trim(),
        residency_class: residency,
        storage_location: storage.trim(),
        retention_terms: retention.trim(),
        training_terms: training.trim(),
        agreement_url: agreement.trim() === "" ? null : agreement.trim(),
        lane_overrides: laneOverrides(laneTimeout, laneAttempts),
      },
    });
  };

  const askAdd = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankAddProblems(slug, label, address, models, key);
    setAddBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({
      kind: "add",
      asked: { slug: slug.trim(), label: label.trim(), base_url: address.trim(), models: modelNames(models), key },
    });
  };

  return (
    <section className="card" aria-labelledby="models-register">
      <h2 id="models-register">{REGISTER_HEADING}</h2>
      <p className="note">{REGISTER_LEDE}</p>
      <p>
        <button type="button" className="button" onClick={download}>
          {DOWNLOAD_REGISTER}
        </button>
      </p>
      {said === null ? null : (
        <p className="note" role="status">
          {said}
        </p>
      )}
      {failure === null ? null : <FailureNotice failure={failure} />}
      {pending === null ? null : (
        <ConfirmAction
          question={
            pending.kind === "terms"
              ? termsQuestion(pending.provider)
              : pending.kind === "retire"
                ? retireQuestion(pending.provider)
                : addQuestion(pending.asked)
          }
          consequence={
            pending.kind === "terms"
              ? termsConsequence(pending.provider, pending.asked)
              : pending.kind === "retire"
                ? RETIRE_CONSEQUENCE
                : ADD_CONSEQUENCE
          }
          confirmLabel={pending.kind === "terms" ? SAVE_TERMS : pending.kind === "retire" ? RETIRE_PROVIDER : ADD_PROVIDER}
          cancelLabel={pending.kind === "terms" ? KEEP_TERMS : pending.kind === "retire" ? KEEP_PROVIDER : DO_NOT_ADD}
          busy={busy}
          onConfirm={() => {
            send(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}
      {body === null ? null : (
        <>
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">Each provider's terms and what it has been sent</caption>
              <thead>
                <tr>
                  <th scope="col">Provider</th>
                  <th scope="col">Terms</th>
                  <th scope="col">Data sent</th>
                  {body.editable ? <th scope="col">Actions</th> : null}
                </tr>
              </thead>
              <tbody>
                {body.providers.map((row) => (
                  <tr key={row.provider}>
                    <td>
                      <code>{row.provider}</code>
                      <p className="note">{row.description}</p>
                    </td>
                    <td>
                      <Terms row={row} />
                    </td>
                    <td>
                      {row.disclosed.length === 0 ? (
                        NOTHING_SENT
                      ) : (
                        <ul aria-label={`Data sent to ${row.provider}`}>
                          {row.disclosed.map((one) => (
                            <li key={one.category}>
                              {one.told}: {String(one.attempts)} calls
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    {body.editable ? (
                      <td>
                        <button
                          type="button"
                          className="button"
                          disabled={busy}
                          aria-label={`${RECORD_TERMS}: ${row.provider}`}
                          onClick={() => {
                            openTerms(row);
                          }}
                        >
                          {RECORD_TERMS}
                        </button>
                        {row.registered?.kind === "openai_compatible" ? (
                          <>
                            {" "}
                            <button
                              type="button"
                              className="button"
                              disabled={busy}
                              aria-label={`${RETIRE_PROVIDER}: ${row.provider}`}
                              onClick={() => {
                                setFailure(null);
                                setPending({ kind: "retire", provider: row.provider });
                              }}
                            >
                              {RETIRE_PROVIDER}
                            </button>
                          </>
                        ) : null}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {editing === null ? null : (
            <form className="form" aria-label={`Terms for ${editing}`} onSubmit={askTerms}>
              <h3>Terms for {editing}</h3>
              <label className="control-label">
                Processing region{" "}
                <input
                  className="form-control"
                  type="text"
                  name="processing_region"
                  value={region}
                  {...problemAttributes(termsProblems, TERMS_FORM, "processing_region")}
                  onChange={(event) => {
                    setRegion(event.target.value);
                  }}
                />
              </label>
              <FieldProblems problems={termsProblems} form={TERMS_FORM} names="processing_region" />
              <label className="control-label">
                Residency{" "}
                <select
                  className="form-control"
                  name="residency_class"
                  value={residency}
                  onChange={(event) => {
                    const chosen = RESIDENCY_CLASSES.find((one) => one === event.target.value);
                    setResidency(chosen ?? "global");
                  }}
                >
                  {RESIDENCY_CLASSES.map((one) => (
                    <option key={one} value={one}>
                      {one.replace("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              <label className="control-label">
                Where it is stored{" "}
                <input
                  className="form-control"
                  type="text"
                  name="storage_location"
                  value={storage}
                  onChange={(event) => {
                    setStorage(event.target.value);
                  }}
                />
              </label>
              <label className="control-label">
                Retention terms{" "}
                <textarea
                  className="form-control"
                  name="retention_terms"
                  value={retention}
                  onChange={(event) => {
                    setRetention(event.target.value);
                  }}
                />
              </label>
              <label className="control-label">
                Training terms{" "}
                <textarea
                  className="form-control"
                  name="training_terms"
                  value={training}
                  onChange={(event) => {
                    setTraining(event.target.value);
                  }}
                />
              </label>
              <label className="control-label">
                Signed agreement (https link){" "}
                <input
                  className="form-control"
                  type="url"
                  name="agreement_url"
                  value={agreement}
                  {...problemAttributes(termsProblems, TERMS_FORM, "terms")}
                  onChange={(event) => {
                    setAgreement(event.target.value);
                  }}
                />
              </label>
              <FieldProblems problems={termsProblems} form={TERMS_FORM} names="terms" />
              <label className="control-label">
                Answer lane timeout in seconds (blank keeps each rung's own){" "}
                <input
                  className="form-control"
                  type="number"
                  name="lane_timeout"
                  min={1}
                  value={laneTimeout}
                  {...problemAttributes(termsProblems, TERMS_FORM, "lane_overrides")}
                  onChange={(event) => {
                    setLaneTimeout(event.target.value);
                  }}
                />
              </label>
              <label className="control-label">
                Answer lane attempts (blank keeps each rung's own){" "}
                <input
                  className="form-control"
                  type="number"
                  name="lane_attempts"
                  min={1}
                  value={laneAttempts}
                  onChange={(event) => {
                    setLaneAttempts(event.target.value);
                  }}
                />
              </label>
              <FieldProblems problems={termsProblems} form={TERMS_FORM} names="lane_overrides" />
              <div className="form-actions">
                <button
                  type="button"
                  className="button"
                  onClick={() => {
                    setEditing(null);
                  }}
                >
                  {KEEP_TERMS}
                </button>{" "}
                <button type="submit" className="button" disabled={busy}>
                  {SAVE_TERMS}
                </button>
              </div>
            </form>
          )}

          {!body.editable ? null : (
            <form className="form" aria-label={ADD_PROVIDER_HEADING} onSubmit={askAdd}>
              <h3>{ADD_PROVIDER_HEADING}</h3>
              <p className="note">{ADD_PROVIDER_NOTE}</p>
              <label className="control-label">
                Short name{" "}
                <input
                  className="form-control"
                  type="text"
                  name="slug"
                  value={slug}
                  {...problemAttributes(addProblems, ADD_FORM, "slug")}
                  onChange={(event) => {
                    setSlug(event.target.value);
                  }}
                />
              </label>
              <FieldProblems problems={addProblems} form={ADD_FORM} names="slug" />
              <label className="control-label">
                What it is{" "}
                <input
                  className="form-control"
                  type="text"
                  name="label"
                  value={label}
                  {...problemAttributes(addProblems, ADD_FORM, "label")}
                  onChange={(event) => {
                    setLabel(event.target.value);
                  }}
                />
              </label>
              <FieldProblems problems={addProblems} form={ADD_FORM} names="label" />
              <label className="control-label">
                Address (https){" "}
                <input
                  className="form-control"
                  type="url"
                  name="base_url"
                  value={address}
                  {...problemAttributes(addProblems, ADD_FORM, ["base_url", "provider"])}
                  onChange={(event) => {
                    setAddress(event.target.value);
                  }}
                />
              </label>
              <FieldProblems problems={addProblems} form={ADD_FORM} names={["base_url", "provider"]} />
              <label className="control-label">
                Model names, one per line{" "}
                <textarea
                  className="form-control"
                  name="models"
                  value={models}
                  {...problemAttributes(addProblems, ADD_FORM, "models")}
                  onChange={(event) => {
                    setModels(event.target.value);
                  }}
                />
              </label>
              <FieldProblems problems={addProblems} form={ADD_FORM} names="models" />
              <label className="control-label">
                Key{" "}
                <input
                  className="form-control"
                  type="text"
                  name="key"
                  autoComplete="off"
                  spellCheck={false}
                  value={key}
                  {...problemAttributes(addProblems, ADD_FORM, "key")}
                  onChange={(event) => {
                    setKey(event.target.value);
                  }}
                />
              </label>
              <FieldProblems problems={addProblems} form={ADD_FORM} names="key" />
              <div className="form-actions">
                <button type="submit" className="button" disabled={busy}>
                  {ADD_PROVIDER}
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}
