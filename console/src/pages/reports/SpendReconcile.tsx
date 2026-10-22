/**
 * Metered spend held against a provider's invoice, under the Spend report (M21.4.1).
 *
 * **Every figure is the API's.** The page asks `GET /report/spend/providers` for a billing period and
 * draws each provider's metered spend, then asks again with an invoice typed in and draws the
 * difference the API worked out, in the invoice's own currency, with the rate it used and the
 * tolerance the verdict was held to. Nothing is converted, subtracted or compared here. A reader the
 * API withheld the provider totals from is told so and shown no figure; spend that no provider can be
 * given is drawn as its own line, so the lines and it are everything the period recorded.
 *
 * **Nothing is stored.** An invoice figure typed here is sent in the address of a read and kept
 * nowhere: the provider holds the invoice, and a copy would be wrong the day a credit note arrives.
 * A blank or malformed field is said beside the form before anything is asked.
 *
 * Task ids: M21.4.1
 */

import { useId, useState, type FormEvent } from "react";
import { useResource } from "../../api/useResource";
import { EmptyList, FailureState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { moneyWords, providersPath, type InvoiceAsked, type SpendByProviderBody } from "../spendQuery";
import { AMOUNT_NEEDED, BUDGET_FORMAT, minorOf } from "../agents/AgentSpend";
import { Quiet } from "./reportParts";

export const RECONCILE_HEADING = "Spend against a provider's invoice";
export const RECONCILE_LEDE = "Hold what this install metered for a billing period against what the provider billed.";
export const PERIOD_NEEDED = "Type the first and the last day of the billing period, as dates.";
export const PERIOD_ORDER = "The billing period ends after it starts.";
export const PROVIDER_NEEDED = "Choose the provider the invoice is from.";
export const CURRENCY_NEEDED = "Type the invoice's currency as three capital letters, such as USD.";
export const WITHHELD_PROVIDERS = "Your reach does not cover the whole company, so provider totals are not shown.";
export const NO_PROVIDERS = "No provider has a price set";
export const NOT_ATTRIBUTED = "Not attributed to a provider";
export const RECONCILES = "Reconciles with the invoice";
export const DOES_NOT_RECONCILE = "Does not reconcile with the invoice";

/** The first and last UTC day of last calendar month, as `YYYY-MM-DD`, from today. */
export function lastMonth(now: Date): { readonly since: string; readonly until: string } {
  const first = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1));
  const next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  return { since: first.toISOString().slice(0, 10), until: next.toISOString().slice(0, 10) };
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;

const SELECT =
  "h-11 min-w-0 max-w-full rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring sm:h-8";

export function SpendReconcile() {
  const [today] = useState(() => new Date());
  const initial = lastMonth(today);
  const [since, setSince] = useState(initial.since);
  const [until, setUntil] = useState(initial.until);
  const [window, setWindow] = useState(initial);
  const [provider, setProvider] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("");
  const [rate, setRate] = useState("");
  const [said, setSaid] = useState<string | null>(null);
  const [asked, setAsked] = useState<InvoiceAsked | null>(null);
  const ids = { since: useId(), until: useId(), provider: useId(), amount: useId(), currency: useId(), rate: useId() };

  const lines = useResource<SpendByProviderBody>(providersPath(window.since, window.until));
  const held = useResource<SpendByProviderBody>(asked === null ? null : providersPath(window.since, window.until, asked));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!DAY.test(since) || !DAY.test(until)) {
      setSaid(PERIOD_NEEDED);
      return;
    }
    if (until <= since) {
      setSaid(PERIOD_ORDER);
      return;
    }
    if (provider === "") {
      setSaid(PROVIDER_NEEDED);
      return;
    }
    if (amount.trim() === "") {
      setSaid(AMOUNT_NEEDED);
      return;
    }
    const minor = minorOf(amount);
    if (minor === null) {
      setSaid(BUDGET_FORMAT);
      return;
    }
    if (!/^[A-Z]{3}$/.test(currency.trim())) {
      setSaid(CURRENCY_NEEDED);
      return;
    }
    setSaid(null);
    setWindow({ since, until });
    setAsked({ provider, invoiceMinor: minor, currency: currency.trim(), rate });
  };

  const body = lines.data;
  const answer = asked === null ? null : held.data?.providers.find((one) => one.provider === asked.provider)?.reconciliation ?? null;
  return (
    <SectionCard title={RECONCILE_HEADING} lede={RECONCILE_LEDE}>
      <div data-slot="spend-reconcile" className="flex min-w-0 flex-col gap-3">
        {lines.failure !== null ? (
          <FailureState failure={lines.failure} />
        ) : body === null ? null : body.withheld ? (
          <Quiet>{WITHHELD_PROVIDERS}</Quiet>
        ) : body.providers.length === 0 ? (
          <EmptyList
            compact
            title={NO_PROVIDERS}
            adds="A provider is listed once a price is set for one of its models on the Models screen."
            by={["super_admin"]}
          />
        ) : (
          <ul aria-label="Metered spend by provider" className="m-0 flex list-none flex-col gap-1 p-0">
            {body.providers.map((one) => (
              <li key={one.provider} className="flex min-w-0 justify-between gap-3 text-sm">
                <span className="min-w-0 [overflow-wrap:anywhere]">{one.provider}</span>
                <span className="tabular-nums">{moneyWords(one.metered_minor, body.currency)}</span>
              </li>
            ))}
            <li className="flex min-w-0 justify-between gap-3 text-sm text-dim">
              <span>{NOT_ATTRIBUTED}</span>
              <span className="tabular-nums">{moneyWords(body.not_attributed_minor, body.currency)}</span>
            </li>
          </ul>
        )}
        {body === null || body.withheld ? null : (
          <form data-slot="spend-reconcile-form" aria-label={RECONCILE_HEADING} onSubmit={submit} className="flex flex-col gap-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.since}>Billing period starts</Label>
              <Input id={ids.since} value={since} placeholder="2026-09-01" onChange={(event) => setSince(event.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.until}>Billing period ends the day before</Label>
              <Input id={ids.until} value={until} placeholder="2026-10-01" onChange={(event) => setUntil(event.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.provider}>Provider</Label>
              <select
                id={ids.provider}
                value={provider}
                onChange={(event) => setProvider(event.target.value)}
                className={SELECT}
              >
                <option value="">Choose a provider</option>
                {body.providers.map((one) => (
                  <option key={one.provider} value={one.provider}>
                    {one.provider}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.amount}>Invoice total</Label>
              <Input id={ids.amount} inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.currency}>Invoice currency</Label>
              <Input id={ids.currency} maxLength={3} value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.rate}>Rate, if the invoice is in another currency than this install</Label>
              <Input id={ids.rate} inputMode="decimal" value={rate} onChange={(event) => setRate(event.target.value)} />
              <span className="text-[11.5px] text-dim">
                How many units of the invoice's currency one unit of this install's currency bought, as the invoice states it.
              </span>
            </div>
            <div>
              <Button type="submit" size="sm" variant="outline" className="min-h-11 sm:min-h-8">
                Hold it against the invoice
              </Button>
            </div>
            {said === null ? null : (
              <p role="alert" className="m-0 text-[12px] text-crit">
                {said}
              </p>
            )}
          </form>
        )}
        {asked === null ? null : held.failure !== null ? (
          <FailureState failure={held.failure} />
        ) : answer === null ? null : (
          <Note kind={answer.within_tolerance ? "done" : "attention"}>
            {answer.within_tolerance ? RECONCILES : DOES_NOT_RECONCILE}. Metered {moneyWords(answer.metered_in_invoice_minor, answer.currency)}, invoiced{" "}
            {moneyWords(answer.invoice_minor, answer.currency)}, difference {moneyWords(answer.difference_minor, answer.currency)}
            {answer.difference_percent === null ? "" : ` (${String(answer.difference_percent)}%)`}, held to {String(answer.tolerance_percent)}%.
            {answer.rate === null ? "" : ` Rate used: ${answer.rate}.`}
          </Note>
        )}
      </div>
    </SectionCard>
  );
}
