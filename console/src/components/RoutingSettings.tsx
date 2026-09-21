/**
 * The Models screen's routing settings: each tier's window and headroom, the residency constraints
 * attached to scopes, and the chain-depth alerts of the last day.
 *
 * `routingSettingsQuery.ts` holds the arguments. Like `ProviderRegister.tsx` it reads nothing of
 * its own: it is handed the providers answer the health card holds, and every write answers with
 * the plan after it, which it hands back to the card. Every write asks first through
 * `components/ConfirmAction.tsx` and is refused by the API without the matrix's write grant over
 * everything, whatever this page drew.
 *
 * Task ids: M5.2.2, M5.5.1, M5.4.8
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure, FieldProblem } from "../api/errors";
import { ConfirmAction } from "./ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import {
  ADD_RESIDENCY,
  ALERTS_CAPTION,
  ALERTS_HEADING,
  ALERTS_LEDE,
  blankResidencyProblems,
  blankTierProblems,
  demandWords,
  DO_NOT_ADD_RESIDENCY,
  EDIT_NUMBERS,
  headroomWords,
  KEEP_NUMBERS,
  KEEP_RESIDENCY,
  KEEP_TIER,
  NO_ALERTS,
  NO_RESIDENCY,
  PRODUCT_DEFAULT,
  readRoutingSettings,
  RESET_CONSEQUENCE,
  RESET_TIER,
  resetQuestion,
  RESIDENCY_API_PATH,
  RESIDENCY_CAPTION,
  RESIDENCY_HEADING,
  RESIDENCY_LEDE,
  residencyAsked,
  residencyConsequence,
  residencyQuestion,
  residencyRetireApiPath,
  RETIRE_RESIDENCY,
  RETIRE_RESIDENCY_CONSEQUENCE,
  retireResidencyQuestion,
  ROUTING_SETTINGS_HEADING,
  ROUTING_SETTINGS_LEDE,
  SAVE_NUMBERS,
  scopeWords,
  SET_HERE,
  tierApiPath,
  tierAsked,
  tierConsequence,
  tierQuestion,
  tierResetApiPath,
  TIERS_CAPTION,
  type ResidencyAsked,
  type ResidencySetting,
  type TierAsked,
} from "../pages/routingSettingsQuery";

const TIER_FORM = "tier";
const RESIDENCY_FORM = "residency";

type Pending =
  | { readonly kind: "tier"; readonly tier: string; readonly asked: TierAsked }
  | { readonly kind: "reset"; readonly tier: string }
  | { readonly kind: "add"; readonly asked: ResidencyAsked }
  | { readonly kind: "retire"; readonly row: ResidencySetting };

function question(pending: Pending): string {
  switch (pending.kind) {
    case "tier":
      return tierQuestion(pending.tier);
    case "reset":
      return resetQuestion(pending.tier);
    case "add":
      return residencyQuestion(pending.asked);
    case "retire":
      return retireResidencyQuestion(pending.row);
  }
}

function consequence(pending: Pending): string {
  switch (pending.kind) {
    case "tier":
      return tierConsequence(pending.tier, pending.asked);
    case "reset":
      return RESET_CONSEQUENCE;
    case "add":
      return residencyConsequence(pending.asked);
    case "retire":
      return RETIRE_RESIDENCY_CONSEQUENCE;
  }
}

const CONFIRM: Record<Pending["kind"], readonly [string, string]> = {
  tier: [SAVE_NUMBERS, KEEP_NUMBERS],
  reset: [RESET_TIER, KEEP_TIER],
  add: [ADD_RESIDENCY, DO_NOT_ADD_RESIDENCY],
  retire: [RETIRE_RESIDENCY, KEEP_RESIDENCY],
};

export function RoutingSettings({
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

  const [editing, setEditing] = useState<string | null>(null);
  const [tokens, setTokens] = useState("");
  const [headroom, setHeadroom] = useState("");
  const [tierBlank, setTierBlank] = useState<FieldProblem[]>([]);

  const [department, setDepartment] = useState("");
  const [wholeCompany, setWholeCompany] = useState(false);
  const [regions, setRegions] = useState("");
  const [onPrem, setOnPrem] = useState(false);
  const [note, setNote] = useState("");
  const [residencyBlank, setResidencyBlank] = useState<FieldProblem[]>([]);

  const settings = readRoutingSettings(data);
  const tierProblems = [...tierBlank, ...(failure?.problems ?? [])];
  const residencyProblems = [...residencyBlank, ...(failure?.problems ?? [])];

  const send = (asked: Pending) => {
    setBusy(true);
    void (async () => {
      const result =
        asked.kind === "tier"
          ? await request<unknown>(tierApiPath(asked.tier), { method: "PUT", body: asked.asked })
          : asked.kind === "reset"
            ? await request<unknown>(tierResetApiPath(asked.tier), { method: "POST" })
            : asked.kind === "add"
              ? await request<unknown>(RESIDENCY_API_PATH, { method: "POST", body: asked.asked })
              : await request<unknown>(residencyRetireApiPath(asked.row.id), { method: "POST" });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      if (asked.kind === "add") {
        setDepartment("");
        setWholeCompany(false);
        setRegions("");
        setOnPrem(false);
        setNote("");
      }
      setEditing(null);
      onWritten(result.data);
    })();
  };

  const askTier = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (editing === null) {
      return;
    }
    setFailure(null);
    const found = blankTierProblems(tokens);
    setTierBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({ kind: "tier", tier: editing, asked: tierAsked(tokens, headroom) });
  };

  const askResidency = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankResidencyProblems(department, wholeCompany, regions, onPrem);
    setResidencyBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({ kind: "add", asked: residencyAsked(department, wholeCompany, regions, onPrem, note) });
  };

  if (settings === null) {
    return null;
  }

  return (
    <section className="card" aria-labelledby="models-routing-settings">
      <h2 id="models-routing-settings">{ROUTING_SETTINGS_HEADING}</h2>
      <p className="note">{ROUTING_SETTINGS_LEDE}</p>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {pending === null ? null : (
        <ConfirmAction
          question={question(pending)}
          consequence={consequence(pending)}
          confirmLabel={CONFIRM[pending.kind][0]}
          cancelLabel={CONFIRM[pending.kind][1]}
          busy={busy}
          onConfirm={() => {
            send(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}

      <div className="grid__scroll">
        <table className="grid__table">
          <caption className="grid__caption">{TIERS_CAPTION}</caption>
          <thead>
            <tr>
              <th scope="col">Tier</th>
              <th scope="col">Window</th>
              <th scope="col">Moves up past</th>
              <th scope="col">Set by</th>
              {settings.editable ? <th scope="col">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {settings.tiers.map((row) => (
              <tr key={row.tier}>
                <td>
                  <code>{row.tier}</code>
                </td>
                <td>{String(row.context_window)} tokens</td>
                <td>{headroomWords(row.escalation_headroom)}</td>
                <td>{row.configured ? SET_HERE : PRODUCT_DEFAULT}</td>
                {settings.editable ? (
                  <td>
                    <button
                      type="button"
                      className="button"
                      disabled={busy}
                      aria-label={`${EDIT_NUMBERS}: ${row.tier}`}
                      onClick={() => {
                        setEditing(row.tier);
                        setTokens(String(row.context_window));
                        setHeadroom(row.configured ? String(row.escalation_headroom) : "");
                        setTierBlank([]);
                        setFailure(null);
                      }}
                    >
                      {EDIT_NUMBERS}
                    </button>
                    {row.configured ? (
                      <>
                        {" "}
                        <button
                          type="button"
                          className="button"
                          disabled={busy}
                          aria-label={`${RESET_TIER}: ${row.tier}`}
                          onClick={() => {
                            setFailure(null);
                            setPending({ kind: "reset", tier: row.tier });
                          }}
                        >
                          {RESET_TIER}
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
        <form className="form" aria-label={`Numbers for the ${editing} tier`} onSubmit={askTier}>
          <h3>Numbers for the {editing} tier</h3>
          <label className="control-label">
            Window, in tokens{" "}
            <input
              className="form-control"
              type="number"
              name="context_window"
              value={tokens}
              {...problemAttributes(tierProblems, TIER_FORM, "context_window")}
              onChange={(event) => {
                setTokens(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={tierProblems} form={TIER_FORM} names="context_window" />
          <label className="control-label">
            Move up past this share of the window, from 0.1 to 1 (blank for the product default){" "}
            <input
              className="form-control"
              type="number"
              step="0.05"
              name="escalation_headroom"
              value={headroom}
              {...problemAttributes(tierProblems, TIER_FORM, "escalation_headroom")}
              onChange={(event) => {
                setHeadroom(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={tierProblems} form={TIER_FORM} names="escalation_headroom" />
          <p>
            <button type="submit" className="button" disabled={busy}>
              {SAVE_NUMBERS}
            </button>
          </p>
        </form>
      )}

      <h3>{RESIDENCY_HEADING}</h3>
      <p className="note">{RESIDENCY_LEDE}</p>
      {settings.residency.length === 0 ? (
        <p className="note">{NO_RESIDENCY}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{RESIDENCY_CAPTION}</caption>
            <thead>
              <tr>
                <th scope="col">Applies to</th>
                <th scope="col">Allowed</th>
                <th scope="col">Note</th>
                <th scope="col">Set by</th>
                {settings.editable ? <th scope="col">Actions</th> : null}
              </tr>
            </thead>
            <tbody>
              {settings.residency.map((row) => (
                <tr key={row.id}>
                  <td>{scopeWords(row.clauses)}</td>
                  <td>{demandWords(row)}</td>
                  <td>{row.note === "" ? "-" : row.note}</td>
                  <td>
                    <code>{row.created_by}</code>
                  </td>
                  {settings.editable ? (
                    <td>
                      <button
                        type="button"
                        className="button"
                        disabled={busy}
                        aria-label={`${RETIRE_RESIDENCY}: ${scopeWords(row.clauses)}`}
                        onClick={() => {
                          setFailure(null);
                          setPending({ kind: "retire", row });
                        }}
                      >
                        {RETIRE_RESIDENCY}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {settings.editable ? (
        <form className="form" aria-label="Add a residency constraint" onSubmit={askResidency}>
          <h3>Add a residency constraint</h3>
          <label className="control-label">
            Department{" "}
            <input
              className="form-control"
              type="text"
              name="department"
              value={department}
              disabled={wholeCompany}
              {...problemAttributes(residencyProblems, RESIDENCY_FORM, "scope")}
              onChange={(event) => {
                setDepartment(event.target.value);
              }}
            />
          </label>
          <label className="control-label">
            <input
              type="checkbox"
              name="whole_company"
              checked={wholeCompany}
              onChange={(event) => {
                setWholeCompany(event.target.checked);
              }}
            />{" "}
            The whole company
          </label>
          <FieldProblems problems={residencyProblems} form={RESIDENCY_FORM} names="scope" />
          <label className="control-label">
            Allowed regions, separated by commas{" "}
            <input
              className="form-control"
              type="text"
              name="allowed_regions"
              value={regions}
              {...problemAttributes(residencyProblems, RESIDENCY_FORM, "allowed_regions")}
              onChange={(event) => {
                setRegions(event.target.value);
              }}
            />
          </label>
          <label className="control-label">
            <input
              type="checkbox"
              name="on_prem_only"
              checked={onPrem}
              onChange={(event) => {
                setOnPrem(event.target.checked);
              }}
            />{" "}
            On the company&apos;s own hardware only
          </label>
          <FieldProblems problems={residencyProblems} form={RESIDENCY_FORM} names="allowed_regions" />
          <label className="control-label">
            Note{" "}
            <input
              className="form-control"
              type="text"
              name="note"
              maxLength={500}
              value={note}
              onChange={(event) => {
                setNote(event.target.value);
              }}
            />
          </label>
          <p>
            <button type="submit" className="button" disabled={busy}>
              {ADD_RESIDENCY}
            </button>
          </p>
        </form>
      ) : null}

      <h3>{ALERTS_HEADING}</h3>
      <p className="note">{ALERTS_LEDE}</p>
      {settings.alerts.length === 0 ? (
        <p className="note">{NO_ALERTS}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{ALERTS_CAPTION}</caption>
            <thead>
              <tr>
                <th scope="col">Raised</th>
                <th scope="col">Level</th>
                <th scope="col">Tier</th>
                <th scope="col">Depth</th>
                <th scope="col">What happened</th>
                <th scope="col">Reference</th>
              </tr>
            </thead>
            <tbody>
              {settings.alerts.map((row) => (
                <tr key={`${row.trace_id}-${row.tier}-${row.raised_at}`}>
                  <td>{row.raised_at}</td>
                  <td>{row.level}</td>
                  <td>
                    <code>{row.tier}</code>
                  </td>
                  <td>{String(row.depth)}</td>
                  <td>{row.reason}</td>
                  <td>
                    <code>{row.trace_id}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
