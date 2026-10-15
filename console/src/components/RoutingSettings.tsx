/**
 * The Routing page's settings, under its Advanced section: each level's size limit and headroom, the rules on where a
 * question may be processed, and the fallback alerts of the last day. Plain words and every input
 * named by its label (`htmlFor`), for the owner's reasons of 2026-09-28.
 *
 * `routingSettingsQuery.ts` holds the arguments. It reads nothing of
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
import type { GridColumn } from "./gridFeatures";
import { GridTable } from "./kit/GridTable";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import {
  ADD_RESIDENCY,
  alertSentence,
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
  severityWords,
  tierApiPath,
  tierAsked,
  tierConsequence,
  tierQuestion,
  tierResetApiPath,
  TIERS_CAPTION,
  type DepthAlert,
  type ResidencyAsked,
  type ResidencySetting,
  type TierAsked,
  type TierSetting,
} from "../pages/routingSettingsQuery";
import { levelName } from "../pages/modelsQuery";

/** The routing alerts, drawn through the console's one grid. Nothing on a row acts, so no closure. */
const ALERT_COLUMNS: GridColumn<DepthAlert>[] = [
  { id: "raised", header: "Raised", cell: ({ row }) => row.original.raised_at },
  { id: "severity", header: "Severity", cell: ({ row }) => severityWords(row.original.level) },
  { id: "level", header: "Level", cell: ({ row }) => levelName(row.original.tier) },
  { id: "tries", header: "Tries", cell: ({ row }) => String(row.original.depth) },
  { id: "what", header: "What happened", cell: ({ row }) => alertSentence(row.original) },
  { id: "reference", header: "Reference", cell: ({ row }) => <code>{row.original.trace_id}</code> },
];

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
  // Fixed ids, one card per page: two mounts draw the same markup, which the tests compare.
  const field = (name: string) => `routing-settings-${name}`;
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

  const tierColumns: GridColumn<TierSetting>[] = [
    { id: "level", header: "Level", cell: ({ row }) => levelName(row.original.tier) },
    { id: "size", header: "Size limit", cell: ({ row }) => `${String(row.original.context_window)} tokens` },
    { id: "headroom", header: "Moves up past", cell: ({ row }) => headroomWords(row.original.escalation_headroom) },
    { id: "set-by", header: "Set by", cell: ({ row }) => (row.original.configured ? SET_HERE : PRODUCT_DEFAULT) },
  ];
  if (settings.editable) {
    tierColumns.push({
      id: "actions",
      header: "Actions",
      cell: ({ row }) => {
        const one = row.original;
        return (
          <>
            <button
              type="button"
              className="button"
              disabled={busy}
              aria-label={`${EDIT_NUMBERS}: ${levelName(one.tier)}`}
              onClick={() => {
                setEditing(one.tier);
                setTokens(String(one.context_window));
                setHeadroom(one.configured ? String(one.escalation_headroom) : "");
                setTierBlank([]);
                setFailure(null);
              }}
            >
              {EDIT_NUMBERS}
            </button>
            {one.configured ? (
              <>
                {" "}
                <button
                  type="button"
                  className="button"
                  disabled={busy}
                  aria-label={`${RESET_TIER}: ${levelName(one.tier)}`}
                  onClick={() => {
                    setFailure(null);
                    setPending({ kind: "reset", tier: one.tier });
                  }}
                >
                  {RESET_TIER}
                </button>
              </>
            ) : null}
          </>
        );
      },
    });
  }

  const residencyColumns: GridColumn<ResidencySetting>[] = [
    { id: "applies-to", header: "Applies to", cell: ({ row }) => scopeWords(row.original.clauses) },
    { id: "allowed", header: "Allowed", cell: ({ row }) => demandWords(row.original) },
    { id: "note", header: "Note", cell: ({ row }) => (row.original.note === "" ? "-" : row.original.note) },
    { id: "set-by", header: "Set by", cell: ({ row }) => <code>{row.original.created_by}</code> },
  ];
  if (settings.editable) {
    residencyColumns.push({
      id: "actions",
      header: "Actions",
      cell: ({ row }) => {
        const one = row.original;
        return (
          <button
            type="button"
            className="button"
            disabled={busy}
            aria-label={`${RETIRE_RESIDENCY}: ${scopeWords(one.clauses)}`}
            onClick={() => {
              setFailure(null);
              setPending({ kind: "retire", row: one });
            }}
          >
            {RETIRE_RESIDENCY}
          </button>
        );
      },
    });
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

      <GridTable
        look="grid"
        caption={TIERS_CAPTION}
        columns={tierColumns}
        rows={settings.tiers}
        rowId={(row) => row.tier}
      />

      {editing === null ? null : (
        <form className="form" aria-label={`Numbers for the ${levelName(editing)} level`} onSubmit={askTier}>
          <h3>Numbers for the {levelName(editing)} level</h3>
          <label className="control-label" htmlFor={field("context_window")}>
            Size limit, in tokens
          </label>
          <input
            id={field("context_window")}
            className="form-control"
            type="number"
            name="context_window"
            value={tokens}
            {...problemAttributes(tierProblems, TIER_FORM, "context_window")}
            onChange={(event) => {
              setTokens(event.target.value);
            }}
          />
          <FieldProblems problems={tierProblems} form={TIER_FORM} names="context_window" />
          <label className="control-label" htmlFor={field("escalation_headroom")}>
            Move up a level past this share of the size limit, from 0.1 to 1 (blank for the product default)
          </label>
          <input
            id={field("escalation_headroom")}
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
        <GridTable
          look="grid"
          caption={RESIDENCY_CAPTION}
          columns={residencyColumns}
          rows={settings.residency}
          rowId={(row) => row.id}
        />
      )}

      {settings.editable ? (
        <form className="form" aria-label="Add a rule on where questions may be processed" onSubmit={askResidency}>
          <h3>Add a rule on where questions may be processed</h3>
          <label className="control-label" htmlFor={field("department")}>
            Department
          </label>
          <input
            id={field("department")}
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
          <label className="control-label" htmlFor={field("whole_company")}>
            <input
              id={field("whole_company")}
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
          <label className="control-label" htmlFor={field("allowed_regions")}>
            Allowed regions, separated by commas
          </label>
          <input
            id={field("allowed_regions")}
            className="form-control"
            type="text"
            name="allowed_regions"
            value={regions}
            {...problemAttributes(residencyProblems, RESIDENCY_FORM, "allowed_regions")}
            onChange={(event) => {
              setRegions(event.target.value);
            }}
          />
          <label className="control-label" htmlFor={field("on_prem_only")}>
            <input
              id={field("on_prem_only")}
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
          <label className="control-label" htmlFor={field("note")}>
            Note
          </label>
          <input
            id={field("note")}
            className="form-control"
            type="text"
            name="note"
            maxLength={500}
            value={note}
            onChange={(event) => {
              setNote(event.target.value);
            }}
          />
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
        <GridTable
          look="grid"
          caption={ALERTS_CAPTION}
          columns={ALERT_COLUMNS}
          rows={settings.alerts}
          rowId={(row) => `${row.trace_id}-${row.tier}-${row.raised_at}`}
        />
      )}
    </section>
  );
}
