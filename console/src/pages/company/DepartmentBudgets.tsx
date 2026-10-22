/**
 * The departments' budgets under the company's: each department's share of the month, its per-run
 * ceiling, the allowance of everyone in it, and the one way money moves from one department to
 * another.
 *
 * **Every line and every control is the API's answer.** `GET /company/budget/departments` returns
 * only the departments the reader holds the budget authority over, and says whether they hold it
 * over everything, so the allocation and the transfer are drawn for that reader alone and a
 * department head sees their own line and the two controls that are theirs. Nothing here totals
 * lines or counts departments: the one figure that is a sum, what the company's budget leaves
 * unshared, is sent by the API and only to a reader who may allocate.
 *
 * **Each act is typed, confirmed, then sent, and a refusal is the API's own sentence.** Amounts are
 * typed in the install's currency and turned into minor units here as the company budget form does
 * (`minorOf`); a share is typed as a percentage of the company's month. A blank field or a figure
 * that is not one is said beside the form before anything is sent, and every act asks first because
 * each writes a new version of a budget that the earlier ones stay behind. **Each form holds its own
 * confirmation and its own call**, so the console's audit follows each write from the button to the
 * route and finds it behind a confirmation.
 *
 * Task ids: M21.1.2, M21.1.3
 */

import { useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { request, type ApiResult } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, EmptyList, FailureState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import {
  DEPARTMENT_BUDGETS_API_PATH,
  DEPARTMENT_TRANSFER_API_PATH,
  departmentAllowancesPath,
  departmentRunCeilingPath,
  readDepartmentBudgets,
} from "../companyQuery";
import { moneyWords } from "../spendQuery";
import { AMOUNT_NEEDED, BUDGET_FORMAT, BUDGET_REASON_FORMAT, minorOf, REASON_NEEDED } from "../agents/AgentSpend";

export const DEPARTMENT_BUDGETS_HEADING = "Department budgets";
export const DEPARTMENT_BUDGETS_LEDE =
  "Each department's share of the company's month, its per-run ceiling, and what each person in it may spend.";
export const NO_DEPARTMENT_BUDGETS = "No department has a budget yet.";
export const UNSHARED = "Not yet shared with a department";
export const SHARE_THE_BUDGET = "Share the budget";
export const MOVE_MONEY = "Move money between departments";
export const SET_RUN_CEILING = "Set the per-run ceiling";
export const GIVE_ALLOWANCES = "Give everyone an allowance";
export const DEPARTMENT_NEEDED = "Type the department's name before sending.";
export const SHARE_FORMAT = "A whole or part percentage of the company's month, such as 40 or 12.5.";
export const SHARE_NEEDED = "Type the share, as a percentage between 0 and 100.";
export const TWO_DEPARTMENTS_NEEDED = "Type the department the money leaves and the one it goes to.";
export const SHARED = "The company's budget is shared as asked.";
export const MOVED = "The money is moved.";
export const CEILING_SET = "The per-run ceiling is set.";
export const ALLOWANCES_GIVEN = "Everyone in the department has their allowance.";
export const CONFIRM_SHARE =
  "It gives the department a version of its monthly budget. Every earlier version stays in its history and on the audit log.";
export const CONFIRM_MOVE =
  "It lowers one department's monthly budget and raises the other's by the same amount, each as a new version.";
export const CONFIRM_CEILING =
  "It replaces the department's per-run ceiling in force from now on. Every earlier one stays in its history.";
export const CONFIRM_ALLOWANCES =
  "It works out a daily and a monthly allowance for each person in the department from its budget, capped so no one person can use most of it. Anyone whose figure would not change is left alone.";

/** The percentage typed, as a fraction between nothing and one, or null when it is not one. */
export function shareOf(typed: string): number | null {
  const text = typed.trim();
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(text)) {
    return null;
  }
  const percent = Number(text);
  return percent > 0 && percent <= 100 ? percent / 100 : null;
}

/** What every form here holds besides its own fields: the reason, the outcome and the pending body. */
function useAction(onSaved: () => void) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [saved, setSaved] = useState(false);
  const [asking, setAsking] = useState<unknown>(null);
  return {
    reason,
    setReason,
    busy,
    said,
    failure,
    saved,
    asking,
    /** Said beside the form before anything is sent. */
    refuse(sentence: string) {
      setSaved(false);
      setFailure(null);
      setSaid(sentence);
    },
    /** Opens the confirmation for a body that passed. */
    ask(body: unknown) {
      setSaved(false);
      setFailure(null);
      setSaid(null);
      setAsking(body);
    },
    cancel() {
      setAsking(null);
    },
    start() {
      setBusy(true);
    },
    finish(result: ApiResult<unknown>) {
      setBusy(false);
      setAsking(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setSaved(true);
      onSaved();
    },
  };
}

type Action = ReturnType<typeof useAction>;

/** The form's frame: its fields, the reason, the button, and what was said or came back. */
function Shell({
  title,
  action,
  done,
  onSubmit,
  children,
}: {
  readonly title: string;
  readonly action: Action;
  readonly done: string;
  readonly onSubmit: () => void;
  readonly children?: ReactNode;
}) {
  const reasonId = useId();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (action.reason.trim() === "") {
      action.refuse(REASON_NEEDED);
      return;
    }
    onSubmit();
  };
  return (
    <form data-slot="department-budget-action" aria-label={title} onSubmit={submit} className="flex flex-col gap-2">
      {children}
      <div className="flex flex-col gap-1">
        <Label htmlFor={reasonId}>Reason</Label>
        <Input id={reasonId} maxLength={200} value={action.reason} onChange={(event) => action.setReason(event.target.value)} />
        <span className="text-[11.5px] text-dim">{BUDGET_REASON_FORMAT}</span>
      </div>
      <div>
        <Button type="submit" size="sm" variant="outline" disabled={action.busy} className="min-h-11 sm:min-h-8">
          {title}
        </Button>
      </div>
      {action.said === null ? null : (
        <p role="alert" className="m-0 text-[12px] text-crit">
          {action.said}
        </p>
      )}
      {action.failure === null ? null : <FailureState failure={action.failure} />}
      {action.saved ? <Note kind="done">{done}</Note> : null}
    </form>
  );
}

function Typed({
  label,
  value,
  onChange,
  decimal = false,
}: {
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly decimal?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} inputMode={decimal ? "decimal" : "text"} value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

function RunCeilingForm({ department, currency, onSaved }: { readonly department: string; readonly currency: string; readonly onSaved: () => void }) {
  const action = useAction(onSaved);
  const [amount, setAmount] = useState("");
  const send = async (body: unknown) => {
    action.start();
    action.finish(await request<unknown>(departmentRunCeilingPath(department), { method: "PUT", body }));
  };
  return (
    <>
      <Shell
        title={SET_RUN_CEILING}
        action={action}
        done={CEILING_SET}
        onSubmit={() => {
          if (amount.trim() === "") {
            action.refuse(AMOUNT_NEEDED);
            return;
          }
          const minor = minorOf(amount);
          if (minor === null) {
            action.refuse(BUDGET_FORMAT);
            return;
          }
          action.ask({ ceiling_minor: minor, reason: action.reason.trim() });
        }}
      >
        <Typed label={`Per-run ceiling for ${department}`} value={amount} onChange={setAmount} decimal />
      </Shell>
      <ConfirmDialog
        open={action.asking !== null}
        question={`Set ${department}'s per-run ceiling to ${moneyWords(minorOf(amount) ?? 0, currency)}?`}
        consequence={CONFIRM_CEILING}
        confirmLabel={SET_RUN_CEILING}
        cancelLabel="Leave it as it is"
        danger={false}
        busy={action.busy}
        onConfirm={() => {
          if (action.asking !== null) {
            void send(action.asking);
          }
        }}
        onCancel={action.cancel}
      />
    </>
  );
}

function AllowancesForm({ department, onSaved }: { readonly department: string; readonly onSaved: () => void }) {
  const action = useAction(onSaved);
  const send = async (body: unknown) => {
    action.start();
    action.finish(await request<unknown>(departmentAllowancesPath(department), { method: "POST", body }));
  };
  return (
    <>
      <Shell
        title={GIVE_ALLOWANCES}
        action={action}
        done={ALLOWANCES_GIVEN}
        onSubmit={() => {
          action.ask({ reason: action.reason.trim() });
        }}
      />
      <ConfirmDialog
        open={action.asking !== null}
        question={`Give everyone in ${department} their allowance?`}
        consequence={CONFIRM_ALLOWANCES}
        confirmLabel={GIVE_ALLOWANCES}
        cancelLabel="Leave it as it is"
        danger={false}
        busy={action.busy}
        onConfirm={() => {
          if (action.asking !== null) {
            void send(action.asking);
          }
        }}
        onCancel={action.cancel}
      />
    </>
  );
}

function ShareForm({ onSaved }: { readonly onSaved: () => void }) {
  const action = useAction(onSaved);
  const [department, setDepartment] = useState("");
  const [percent, setPercent] = useState("");
  const send = async (body: unknown) => {
    action.start();
    action.finish(await request<unknown>(DEPARTMENT_BUDGETS_API_PATH, { method: "PUT", body }));
  };
  return (
    <>
      <Shell
        title={SHARE_THE_BUDGET}
        action={action}
        done={SHARED}
        onSubmit={() => {
          if (department.trim() === "") {
            action.refuse(DEPARTMENT_NEEDED);
            return;
          }
          const share = shareOf(percent);
          if (share === null) {
            action.refuse(SHARE_NEEDED);
            return;
          }
          action.ask({ shares: [{ department: department.trim(), share }], reason: action.reason.trim() });
        }}
      >
        <Typed label="Department" value={department} onChange={setDepartment} />
        <Typed label="Share of the company's month (%)" value={percent} onChange={setPercent} decimal />
        <span className="text-[11.5px] text-dim">{SHARE_FORMAT}</span>
      </Shell>
      <ConfirmDialog
        open={action.asking !== null}
        question={`Give ${department.trim()} ${percent.trim()}% of the company's month?`}
        consequence={CONFIRM_SHARE}
        confirmLabel={SHARE_THE_BUDGET}
        cancelLabel="Leave it as it is"
        danger={false}
        busy={action.busy}
        onConfirm={() => {
          if (action.asking !== null) {
            void send(action.asking);
          }
        }}
        onCancel={action.cancel}
      />
    </>
  );
}

function TransferForm({ currency, onSaved }: { readonly currency: string; readonly onSaved: () => void }) {
  const action = useAction(onSaved);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [amount, setAmount] = useState("");
  const send = async (body: unknown) => {
    action.start();
    action.finish(await request<unknown>(DEPARTMENT_TRANSFER_API_PATH, { method: "POST", body }));
  };
  return (
    <>
      <Shell
        title={MOVE_MONEY}
        action={action}
        done={MOVED}
        onSubmit={() => {
          if (from.trim() === "" || to.trim() === "" || from.trim() === to.trim()) {
            action.refuse(TWO_DEPARTMENTS_NEEDED);
            return;
          }
          if (amount.trim() === "") {
            action.refuse(AMOUNT_NEEDED);
            return;
          }
          const minor = minorOf(amount);
          if (minor === null) {
            action.refuse(BUDGET_FORMAT);
            return;
          }
          action.ask({
            from_department: from.trim(),
            to_department: to.trim(),
            amount_minor: minor,
            reason: action.reason.trim(),
          });
        }}
      >
        <Typed label="From department" value={from} onChange={setFrom} />
        <Typed label="To department" value={to} onChange={setTo} />
        <Typed label="Amount" value={amount} onChange={setAmount} decimal />
      </Shell>
      <ConfirmDialog
        open={action.asking !== null}
        question={`Move ${moneyWords(minorOf(amount) ?? 0, currency)} from ${from.trim()} to ${to.trim()}?`}
        consequence={CONFIRM_MOVE}
        confirmLabel={MOVE_MONEY}
        cancelLabel="Leave it as it is"
        danger={false}
        busy={action.busy}
        onConfirm={() => {
          if (action.asking !== null) {
            void send(action.asking);
          }
        }}
        onCancel={action.cancel}
      />
    </>
  );
}

function Money({ minor, currency }: { readonly minor: number | null; readonly currency: string }): ReactNode {
  return minor === null ? "none set" : moneyWords(minor, currency);
}

/** The section, or nothing for a reader the answer offers nothing to. */
export function DepartmentBudgets({ refresh }: { readonly refresh: number }) {
  // Moved by an act here, and added to the page's own, so an act asks this section again without
  // asking the page's figures again, which would replace the sentence that says the act worked.
  const [changed, setChanged] = useState(0);
  const onChanged = () => {
    setChanged((one) => one + 1);
  };
  const answer = useResource<unknown>(DEPARTMENT_BUDGETS_API_PATH, refresh + changed);
  const read = answer.data === null ? null : readDepartmentBudgets(answer.data);
  // While it is asked again the last answer stays drawn, so the sentence saying an act worked is
  // still beside the form that did it; `useResource` clears its data for each asking.
  const last = useRef<ReturnType<typeof readDepartmentBudgets>>(null);
  if (read !== null) {
    last.current = read;
  }
  const found = read ?? (answer.busy ? last.current : null);
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (found === null || (found.lines.length === 0 && !found.mayAllocate)) {
    return null;
  }
  const { currency } = found;
  return (
    <SectionCard title={DEPARTMENT_BUDGETS_HEADING} lede={DEPARTMENT_BUDGETS_LEDE}>
      <div data-slot="department-budgets" className="flex min-w-0 flex-col gap-4">
        {found.unallocatedMinor === null ? null : (
          <p className="m-0 text-sm">
            <span className="text-dim">{UNSHARED}: </span>
            <span className="tabular-nums">{moneyWords(found.unallocatedMinor, currency)}</span>
          </p>
        )}
        {found.lines.length === 0 ? (
          <EmptyList
            compact
            title={NO_DEPARTMENT_BUDGETS}
            adds="A department is listed here once the company's month is shared with it, by the form below."
            by={["super_admin"]}
          />
        ) : (
          <ul aria-label={DEPARTMENT_BUDGETS_HEADING} className="m-0 flex list-none flex-col gap-4 p-0">
            {found.lines.map((line) => (
              <li key={line.department} data-slot="department-budget-line" className="flex min-w-0 flex-col gap-2">
                <div className="flex min-w-0 flex-wrap justify-between gap-x-3 text-sm">
                  <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{line.department}</span>
                  <span className="tabular-nums">
                    Month: <Money minor={line.monthlyMinor} currency={currency} />. Per run:{" "}
                    <Money minor={line.runCeilingMinor} currency={currency} />.
                  </span>
                </div>
                <RunCeilingForm department={line.department} currency={currency} onSaved={onChanged} />
                <AllowancesForm department={line.department} onSaved={onChanged} />
              </li>
            ))}
          </ul>
        )}
        {found.mayAllocate ? (
          <>
            <ShareForm onSaved={onChanged} />
            <TransferForm currency={currency} onSaved={onChanged} />
          </>
        ) : null}
      </div>
    </SectionCard>
  );
}
