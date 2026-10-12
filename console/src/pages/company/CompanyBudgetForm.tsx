/**
 * The control that sets the company's monthly budget, offered only to a reader the consumption
 * answer says may set it.
 *
 * **It sends what was typed after a confirmation, and says the API's sentence when it refuses.**
 * The amount is typed in the install's currency and turned into minor units here, as the agent's
 * own budget form does it (`minorOf`); a blank field, an amount that is not one and a missing reason
 * are each said beside the form before anything is sent, and the budget is set only from a
 * confirmation, because it replaces the one in force and the earlier ones stay in its history. A
 * refusal is the API's own sentence, which names the role that would let the reader set it.
 *
 * Task ids: M33.1.1.3
 */

import { useId, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import { ConfirmDialog, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { COMPANY_BUDGET_API_PATH } from "../companyQuery";
import { moneyWords } from "../spendQuery";
import { AMOUNT_NEEDED, BUDGET_FORMAT, BUDGET_REASON_FORMAT, minorOf, REASON_NEEDED } from "../agents/AgentSpend";

export const SET_COMPANY_BUDGET = "Set the company's monthly budget";
export const COMPANY_BUDGET_SAVED = "The company's monthly budget is saved.";
export const COMPANY_BUDGET_CONSEQUENCE =
  "It replaces the company's budget in force from now on. Every earlier budget stays in its history and on the audit log.";

export function CompanyBudgetForm({ currency, onSaved }: { readonly currency: string; readonly onSaved: () => void }) {
  const amountId = useId();
  const reasonId = useId();
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  // The ceiling asked for, held while the confirmation is open.
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
    const result = await request<unknown>(COMPANY_BUDGET_API_PATH, {
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
    <form data-slot="company-budget-form" onSubmit={submit} className="flex flex-col gap-2">
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
          {SET_COMPANY_BUDGET}
        </Button>
      </div>
      {said === null ? null : (
        <p role="alert" className="m-0 text-[12px] text-crit">
          {said}
        </p>
      )}
      {done ? <Note kind="done">{COMPANY_BUDGET_SAVED}</Note> : null}
      <ConfirmDialog
        open={asking !== null}
        question={`Set the company's monthly budget to ${moneyWords(asking ?? 0, currency)}?`}
        consequence={COMPANY_BUDGET_CONSEQUENCE}
        confirmLabel={SET_COMPANY_BUDGET}
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
