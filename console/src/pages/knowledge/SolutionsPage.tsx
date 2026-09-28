/**
 * Solutions, a tab of Knowledge: a fix found in a conversation, captured for one department, and
 * approved into a verified document by somebody who may add documents there (M7.6.2).
 *
 * **Two lists, each the reader's own.** What waits for their decision, which is a solution captured
 * in a department they may add documents to by somebody else; and what they captured, with where
 * each got to. The capturer never decides their own, which the API refuses and this page does not
 * offer. Nothing here is a count of anybody else's solutions.
 *
 * **Capturing is a drawer that says what it takes before it is sent**: what it solved, the solution,
 * and the department it is for, from the departments the API says this reader may capture in. To
 * somebody who may capture nowhere the action is not drawn.
 *
 * **What was removed from the old card, and why.** The capturer's and the decider's principal ids,
 * now names; and the capture form, the waiting list and the reader's own list stacked on the
 * Knowledge page above the library, which is this tab now.
 *
 * Task ids: M7.6.2, M27.16.1
 */

import { Lightbulb, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Drawer, EmptyState, Fact, FactList, FailureState, LoadingState, PageHeader, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import { defaultReviewDay, instantOf, LIFECYCLE_FIELDS, SOLUTIONS_API_PATH, solutionDecisionPath } from "../knowledgeLifecycleQuery";
import { REVIEW_HINT, REVIEW_LABEL, reviewProblem } from "./formParts";
import { dayWords, documentAddress, KNOWLEDGE_HEADING, LIBRARY_ADDRESS } from "./knowledgeDocuments";

export const SOLUTIONS_HEADING = "Solutions";
export const SOLUTIONS_LEDE =
  "A fix found in a conversation becomes company knowledge when somebody who may add documents to its department approves it.";
export const LOADING_SOLUTIONS = "Loading solutions.";
export const CAPTURE = "Capture a solution";
export const CAPTURE_DESCRIPTION = "It waits for somebody else who may add documents to the department. You cannot approve your own.";
export const WAITING_HEADING = "Waiting for your decision";
export const YOURS_HEADING = "Solutions you captured";
export const NONE_WAITING = "Nothing is waiting for your decision";
export const NONE_WAITING_DESCRIPTION = "A solution somebody captures in a department where you add documents appears here.";
export const NONE_YOURS = "You have captured no solutions";
export const NONE_YOURS_DESCRIPTION = "Capture one from a conversation that fixed something, so the next person finds the fix.";
export const APPROVE = "Approve";
export const REFUSE = "Refuse";

export const CAPTURE_PROBLEMS = {
  problem: "Say what it solved.",
  answer: "Say what the solution is.",
  department: "Choose the department it is for.",
} as const;

/** One captured solution, as this console holds it. */
export interface SolutionRow {
  readonly solutionId: string;
  readonly department: string;
  readonly problem: string;
  readonly answer: string;
  readonly state: string;
  readonly capturedByName?: string;
  readonly capturedAt?: string;
  readonly decidedByName?: string;
  readonly decidedAt?: string;
  readonly itemId?: string;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function readSolution(value: unknown): SolutionRow | null {
  const row = typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
  const solutionId = said(row?.["solution_id"]);
  if (row === null || solutionId === undefined) {
    return null;
  }
  const optional = (key: string, from: string): Record<string, string> => {
    const found = said(row[from]);
    return found === undefined ? {} : { [key]: found };
  };
  return {
    solutionId,
    department: said(row["department"]) ?? "",
    problem: said(row["problem"]) ?? "",
    answer: said(row["answer"]) ?? "",
    state: said(row["state"]) ?? "pending",
    ...optional("capturedByName", "captured_by_name"),
    ...optional("capturedAt", "captured_at"),
    ...optional("decidedByName", "decided_by_name"),
    ...optional("decidedAt", "decided_at"),
    ...optional("itemId", "item_id"),
  };
}

/** `SolutionsView` as this console holds it. */
export function readSolutions(payload: unknown): {
  readonly waiting: readonly SolutionRow[];
  readonly yours: readonly SolutionRow[];
  readonly departments: readonly string[];
} {
  const body = typeof payload === "object" && payload !== null ? (payload as Record<string, unknown>) : {};
  const list = (key: string): SolutionRow[] =>
    (Array.isArray(body[key]) ? (body[key] as readonly unknown[]) : []).flatMap((one) => {
      const row = readSolution(one);
      return row === null ? [] : [row];
    });
  const departments = Array.isArray(body["departments"])
    ? (body["departments"] as readonly unknown[]).filter((one): one is string => typeof one === "string")
    : [];
  return { waiting: list("waiting"), yours: list("yours"), departments };
}

export function stateWords(state: string): string {
  switch (state) {
    case "approved":
      return "Approved, and now company knowledge";
    case "rejected":
      return "Not approved";
    default:
      return "Waiting for a decision";
  }
}

const SELECT =
  "h-11 w-full min-w-0 rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring sm:h-9";

function CaptureForm({ departments, onDone }: { readonly departments: readonly string[]; readonly onDone: () => void }) {
  const [problem, setProblem] = useState("");
  const [answer, setAnswer] = useState("");
  const [department, setDepartment] = useState(departments.length === 1 ? (departments[0] ?? "") : "");
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = [
      ...(problem.trim() === "" ? [CAPTURE_PROBLEMS.problem] : []),
      ...(answer.trim() === "" ? [CAPTURE_PROBLEMS.answer] : []),
      ...(department === "" ? [CAPTURE_PROBLEMS.department] : []),
    ];
    setProblems(found);
    if (found.length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(SOLUTIONS_API_PATH, {
        method: "POST",
        body: { problem: problem.trim(), answer: answer.trim(), department, conversation_ref: "" },
      });
      setBusy(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        setProblem("");
        setAnswer("");
        onDone();
      }
    })();
  };

  const shown = (one: string) =>
    problems.includes(one) ? (
      <p key={one} className="m-0 text-[12.5px] text-crit">
        {one}
      </p>
    ) : null;
  return (
    <form className="flex min-w-0 flex-col gap-4" aria-label={CAPTURE} onSubmit={onSubmit} noValidate>
      {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
      <div className="flex flex-col gap-1.5">
        <label htmlFor="solution-problem" className="text-[13px] font-medium text-ink">
          What it solved
        </label>
        <Textarea id="solution-problem" name="problem" maxLength={2000} value={problem} onChange={(event) => setProblem(event.target.value)} />
        <p className="m-0 text-[12px] text-dim">The question or problem, in a sentence or two. Up to 2,000 characters.</p>
        {shown(CAPTURE_PROBLEMS.problem)}
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="solution-answer" className="text-[13px] font-medium text-ink">
          The solution
        </label>
        <Textarea id="solution-answer" name="answer" maxLength={20000} value={answer} onChange={(event) => setAnswer(event.target.value)} />
        <p className="m-0 text-[12px] text-dim">What fixed it, as the next person should read it. Up to 20,000 characters.</p>
        {shown(CAPTURE_PROBLEMS.answer)}
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="solution-department" className="text-[13px] font-medium text-ink">
          Department
        </label>
        <select id="solution-department" name="department" className={SELECT} value={department} onChange={(event) => setDepartment(event.target.value)}>
          <option value="">Choose one</option>
          {departments.map((one) => (
            <option key={one} value={one}>
              {one}
            </option>
          ))}
        </select>
        {shown(CAPTURE_PROBLEMS.department)}
      </div>
      <div className="flex justify-end">
        <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
          {CAPTURE}
        </Button>
      </div>
    </form>
  );
}

function DecideForm({ one, onDone }: { readonly one: SolutionRow; readonly onDone: () => void }) {
  const [day, setDay] = useState(defaultReviewDay());
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const decide = (verdict: "approved" | "rejected", reviewBy: string | null) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(solutionDecisionPath(one.solutionId), {
        method: "POST",
        body: { verdict, review_by: reviewBy },
      });
      setBusy(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = reviewProblem(day);
    setProblem(found);
    const instant = instantOf(day);
    if (found !== null || instant === null) {
      return;
    }
    decide("approved", instant);
  };

  return (
    <form className="flex min-w-0 flex-col gap-3" aria-label={`Decide ${one.problem}`} onSubmit={onSubmit} noValidate>
      {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`review-${one.solutionId}`} className="text-[13px] font-medium text-ink">
          {REVIEW_LABEL}
        </label>
        <Input id={`review-${one.solutionId}`} type="date" name="review_by" className="h-11 sm:h-9" value={day} onChange={(event) => setDay(event.target.value)} />
        <p className="m-0 text-[12px] text-dim">{REVIEW_HINT} Needed to approve.</p>
        {problem === null ? null : <p className="m-0 text-[12.5px] text-crit">{problem}</p>}
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="outline" className="min-h-11 sm:min-h-9" disabled={busy} onClick={() => decide("rejected", null)}>
          {REFUSE}
        </Button>
        <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
          {APPROVE}
        </Button>
      </div>
    </form>
  );
}

function Facts({ one }: { readonly one: SolutionRow }) {
  return (
    <FactList>
      <Fact label="What it solved">{one.problem}</Fact>
      <Fact label="The solution">
        <span className="whitespace-pre-wrap">{one.answer}</span>
      </Fact>
      <Fact label="Department">{one.department}</Fact>
      <Fact label="Captured">
        {[one.capturedByName, dayWords(one.capturedAt)].filter((part): part is string => part !== undefined).join(", ") || "Not recorded"}
      </Fact>
      <Fact label="State">
        {stateWords(one.state)}
        {one.itemId === undefined ? null : (
          <>
            {" "}
            <Link to={documentAddress(one.itemId)} className="text-acc-text underline-offset-4 hover:underline">
              Open the document
            </Link>
          </>
        )}
      </Fact>
    </FactList>
  );
}

export function SolutionsPage() {
  const [version, setVersion] = useState(0);
  const changed = () => {
    setVersion((was) => was + 1);
  };
  const answer = useResource<unknown>(SOLUTIONS_API_PATH, version);
  const [capturing, setCapturing] = useState(false);
  const found = answer.failure === null && !answer.busy ? readSolutions(answer.data) : null;

  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.busy || found === null) {
    body = <LoadingState label={LOADING_SOLUTIONS} />;
  } else {
    body = (
      <>
        <SectionCard title={WAITING_HEADING}>
          {found.waiting.length === 0 ? (
            <EmptyState title={NONE_WAITING} description={NONE_WAITING_DESCRIPTION} icon={<Lightbulb aria-hidden />} />
          ) : (
            <ul className="m-0 flex list-none flex-col gap-4 p-0">
              {found.waiting.map((one) => (
                <li key={one.solutionId} className="flex min-w-0 flex-col gap-3 border-b border-line pb-4 last:border-b-0 last:pb-0">
                  <Facts one={one} />
                  <DecideForm one={one} onDone={changed} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
        <SectionCard title={YOURS_HEADING}>
          {found.yours.length === 0 ? (
            <EmptyState title={NONE_YOURS} description={NONE_YOURS_DESCRIPTION} />
          ) : (
            <ul className="m-0 flex list-none flex-col gap-4 p-0">
              {found.yours.map((one) => (
                <li key={one.solutionId} className="border-b border-line pb-4 last:border-b-0 last:pb-0">
                  <Facts one={one} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </>
    );
  }

  return (
    <div data-slot="solutions-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: KNOWLEDGE_HEADING, to: LIBRARY_ADDRESS }, { label: SOLUTIONS_HEADING }]}
        title={SOLUTIONS_HEADING}
        lede={SOLUTIONS_LEDE}
        primary={
          found !== null && found.departments.length > 0 ? (
            <Button
              className="min-h-11 sm:min-h-9"
              onClick={() => {
                setCapturing(true);
              }}
            >
              <Plus aria-hidden /> {CAPTURE}
            </Button>
          ) : undefined
        }
      />
      {body}
      {found === null ? null : (
        <Drawer open={capturing} onOpenChange={setCapturing} title={CAPTURE} description={CAPTURE_DESCRIPTION}>
          <CaptureForm
            departments={found.departments}
            onDone={() => {
              setCapturing(false);
              changed();
            }}
          />
        </Drawer>
      )}
    </div>
  );
}
