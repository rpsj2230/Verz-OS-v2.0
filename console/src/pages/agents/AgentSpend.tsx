/**
 * The Dashboard's money: who the agent's cost is attributed to, and where its month is heading
 * against its own monthly budget.
 *
 * **Cost per person is the route's list, drawn as sent (M39.1.3.3).** Heaviest first, a name and an
 * amount, and never a share or a remainder: a reader of their own spend is sent their own row and
 * nothing else, so the card says "your runs" under it and draws no "everybody else" line, which
 * would be everybody else's spend by subtraction.
 *
 * **The projection is drawn only when the route sent one (M39.1.3.4)**, which is for a reader of
 * everybody's spend with a monthly budget set. With no budget set, such a reader is told so and
 * offered the one control that sets it; the amount is typed in the install's currency, the format
 * is said before anything is sent, and a refusal is the API's sentence, which names the role that
 * would let them. A blank field is said beside the form before anything is sent, and a budget is set
 * only from a confirmation, because it replaces the one in force.
 *
 * Task ids: M39.1.3.3, M39.1.3.4
 */

import { useId, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import { ConfirmDialog, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { basisWords, costWords, type AgentPeriod, type Projection } from "./agentStats";

export const COST_BY_PERSON = "Cost by person";
export const NOBODY_SPENT = "Nothing was spent through this agent in this period.";
export const MONTH_HEADING = "This month against its budget";
export const NO_BUDGET = "No monthly budget is set for this agent, so there is nothing to project against.";
export const SET_BUDGET = "Set monthly budget";
export const BUDGET_FORMAT = "An amount in the install's currency, such as 250 or 250.50.";
export const BUDGET_REASON_FORMAT = "Why, in a sentence of up to 200 characters.";
export const BUDGET_SAVED = "The monthly budget is saved. The projection now reads against it.";
export const AMOUNT_NEEDED = "Type the monthly budget before setting it.";
export const REASON_NEEDED = "Say why the budget is being set, so the change can be followed later.";
export const BUDGET_CONSEQUENCE =
  "It replaces the budget in force from now on. Every earlier budget stays in this agent's history and on the audit log.";
export const OVER_BUDGET = "At this pace the month ends over its budget.";
export const WITHIN_BUDGET = "At this pace the month ends within its budget.";

/** Where one agent's monthly budget is set, under the API base. */
export function agentBudgetApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/budget`;
}

/** An amount typed in major units, as minor units, or null when it is not one. */
export function minorOf(typed: string): number | null {
  const text = typed.trim();
  if (!/^\d{1,9}(\.\d{1,2})?$/.test(text)) {
    return null;
  }
  const [whole = "0", part = ""] = text.split(".");
  const minor = Number(whole) * 100 + Number(part.padEnd(2, "0"));
  return minor >= 1 ? minor : null;
}

export function CostByPerson({
  period,
  currency,
  costBasis,
}: {
  readonly period: AgentPeriod | undefined;
  readonly currency: string | undefined;
  readonly costBasis: string | undefined;
}) {
  if (period === undefined || period.costMinor === undefined) {
    return null;
  }
  return (
    <SectionCard title={COST_BY_PERSON} lede="Who this agent's cost comes from in the period chosen, heaviest first.">
      {period.callers.length === 0 ? (
        <Note>{NOBODY_SPENT}</Note>
      ) : (
        <ul data-slot="cost-by-person" className="m-0 flex list-none flex-col p-0">
          {period.callers.map((one) => (
            <li
              key={one.principalId}
              className="[display:grid] grid-cols-[minmax(0,1fr)_auto] gap-x-3 border-b border-line py-2 text-[13px] last:border-b-0"
            >
              <span className="min-w-0 text-ink [overflow-wrap:anywhere]">{one.name ?? "Not named in the directory"}</span>
              <span className="font-mono text-body">{costWords(one.spendMinor, currency)}</span>
            </li>
          ))}
        </ul>
      )}
      {basisWords(costBasis) === undefined ? null : (
        <div className="mt-2">
          <Note>{`Counted over ${basisWords(costBasis) ?? ""}.`}</Note>
        </div>
      )}
    </SectionCard>
  );
}

function BudgetForm({
  agentId,
  currency,
  onSaved,
}: {
  readonly agentId: string;
  readonly currency: string | undefined;
  readonly onSaved: () => void;
}) {
  const amountId = useId();
  const reasonId = useId();
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  // The ceiling the person asked for, held while the confirmation is open.
  const [asking, setAsking] = useState<number | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (amount.trim() === "") {
      setSaid(AMOUNT_NEEDED);
      return;
    }
    const minor = minorOf(amount);
    if (minor === null) {
      setSaid(BUDGET_FORMAT);
      return;
    }
    if (reason.trim() === "") {
      setSaid(REASON_NEEDED);
      return;
    }
    setSaid(null);
    setAsking(minor);
  };

  const send = async (minor: number) => {
    setBusy(true);
    const result = await request<unknown>(agentBudgetApiPath(agentId), {
      method: "PUT",
      body: { ceiling_minor: minor, reason: reason.trim() },
    });
    setBusy(false);
    setAsking(null);
    if (!result.ok) {
      setSaid(result.failure.message);
      return;
    }
    setSaid(null);
    setDone(true);
    onSaved();
  };

  return (
    <form data-slot="budget-form" onSubmit={submit} className="flex flex-col gap-2">
      <div className="flex flex-col gap-1">
        <Label htmlFor={amountId}>Monthly budget</Label>
        <Input id={amountId} inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} aria-describedby={`${amountId}-format`} />
        <span id={`${amountId}-format`} className="text-[11.5px] text-dim">
          {BUDGET_FORMAT}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={reasonId}>Reason</Label>
        <Input id={reasonId} maxLength={200} value={reason} onChange={(event) => setReason(event.target.value)} aria-describedby={`${reasonId}-format`} />
        <span id={`${reasonId}-format`} className="text-[11.5px] text-dim">
          {BUDGET_REASON_FORMAT}
        </span>
      </div>
      <div>
        <Button type="submit" size="sm" variant="outline" disabled={busy} className="min-h-11 sm:min-h-8">
          {SET_BUDGET}
        </Button>
      </div>
      {said === null ? null : (
        <p role="alert" className="m-0 text-[12px] text-crit">
          {said}
        </p>
      )}
      {done ? <Note kind="done">{BUDGET_SAVED}</Note> : null}
      <ConfirmDialog
        open={asking !== null}
        question={`Set this agent's monthly budget to ${costWords(asking ?? 0, currency) ?? ""}?`}
        consequence={BUDGET_CONSEQUENCE}
        confirmLabel={SET_BUDGET}
        cancelLabel="Keep the budget as it is"
        danger={false}
        busy={busy}
        onConfirm={() => {
          if (asking !== null) {
            void send(asking);
          }
        }}
        onCancel={() => {
          setAsking(null);
        }}
      />
    </form>
  );
}

export function MonthAgainstBudget({
  agentId,
  projection,
  currency,
  costBasis,
  recorded,
  onSaved,
}: {
  readonly agentId: string;
  readonly projection: Projection | undefined;
  readonly currency: string | undefined;
  readonly costBasis: string | undefined;
  /** Whether anything records a run's cost; with nothing recorded there is no month to project. */
  readonly recorded: boolean;
  readonly onSaved: () => void;
}) {
  // A reader of their own spend is never sent a projection and is not offered the budget: the
  // month to date is everybody's, and so is the ceiling's headroom.
  if (!recorded || costBasis !== "everyone") {
    return null;
  }
  return (
    <SectionCard title={MONTH_HEADING} lede="Where this month ends if the agent keeps its pace, against its own monthly budget.">
      {projection === undefined ? (
        <div className="flex flex-col gap-3">
          <Note>{NO_BUDGET}</Note>
          <BudgetForm agentId={agentId} currency={currency} onSaved={onSaved} />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <dl data-slot="projection" className="m-0 [display:grid] grid-cols-3 gap-2 text-[13px]">
            <div>
              <dt className="text-[11.5px] text-dim">Spent so far</dt>
              <dd className="m-0 font-mono text-ink">{costWords(projection.spentMinor, currency)}</dd>
            </div>
            <div>
              <dt className="text-[11.5px] text-dim">Month end, at this pace</dt>
              <dd className="m-0 font-mono text-ink">{costWords(projection.projectedMinor, currency)}</dd>
            </div>
            <div>
              <dt className="text-[11.5px] text-dim">Monthly budget</dt>
              <dd className="m-0 font-mono text-ink">{costWords(projection.ceilingMinor, currency)}</dd>
            </div>
          </dl>
          <Note>{projection.overCeiling ? OVER_BUDGET : WITHIN_BUDGET}</Note>
          <BudgetForm agentId={agentId} currency={currency} onSaved={onSaved} />
        </div>
      )}
    </SectionCard>
  );
}
