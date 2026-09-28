/**
 * The Knowledge module's small parts: a document's state and review as pills, and a person's own
 * knowledge tasks with the one write a task takes.
 *
 * **The word carries the meaning and the colour repeats it**, as `pages/agents/pills.tsx` draws an
 * agent's state, so a pill reads the same to somebody who cannot tell the colours apart, and a state
 * this console has not heard of is drawn as itself in the plain tone.
 *
 * **A task is the reader's own and says one document by name.** The list and a document's Dashboard
 * draw the tasks the database opened for this person (`brain.knowledge.lifecycle.TaskKind`); a
 * review is closed by verifying the document, so only a task that reports offers Mark as read.
 *
 * Task ids: M7.4.6, M7.7.2, M27.16.1
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { Button } from "../../components/ui/button";
import { cn } from "../../lib/utils";
import { FailureNotice } from "../../ui/FailureNotice";
import { taskDonePath } from "../knowledgeLifecycleQuery";
import { documentAddress, SOLUTIONS_ADDRESS, stateWords, type TaskRow } from "./knowledgeDocuments";

const STATE_TONE: Readonly<Record<string, string>> = {
  published: "bg-ok-wash text-ok",
  superseded: "bg-sunk text-dim",
  archived: "bg-sunk text-dim",
  draft: "bg-warn-wash text-warn",
};

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em] whitespace-nowrap";

export function StatePill({ state }: { readonly state: string }) {
  return (
    <span data-slot="state-pill" className={cn(PILL, STATE_TONE[state] ?? "bg-sunk text-ink")}>
      {stateWords(state)}
    </span>
  );
}

/** A review date that has arrived. Drawn only then: a date not yet due needs no pill. */
export function DuePill() {
  return <span className={cn(PILL, "bg-warn-wash text-warn")}>Review due</span>;
}

export const MARK_READ = "Mark as read";
export const OPEN_TASK = "Open";

/** The reader's own tasks, each with a way to what it is about and, where it reports, Mark as read. */
export function TaskList({ tasks, onChanged }: { readonly tasks: readonly TaskRow[]; readonly onChanged: () => void }) {
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const markRead = (taskId: string) => {
    void (async () => {
      const result = await request<unknown>(taskDonePath(taskId), { method: "POST" });
      setFailure(result.ok ? null : result.failure);
      onChanged();
    })();
  };
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {failure === null ? null : <FailureNotice failure={failure} />}
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {tasks.map((one) => (
          <li key={one.taskId} className="flex min-w-0 flex-col gap-2 border-b border-line pb-2 last:border-b-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
            <span className="min-w-0 text-[13px] text-ink [overflow-wrap:anywhere]">{one.says}</span>
            <span className="flex shrink-0 items-center gap-2">
              <Button asChild variant="ghost" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
                <Link to={one.kind === "solution_decided" ? SOLUTIONS_ADDRESS : documentAddress(one.itemId)}>{OPEN_TASK}</Link>
              </Button>
              {one.closable ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="min-h-11 sm:min-h-8"
                  onClick={() => {
                    markRead(one.taskId);
                  }}
                >
                  {MARK_READ}
                </Button>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
