/**
 * The head of a stepped flow: "Step 2 of 6", a bar showing how far along it is, and a numbered
 * button for each step so any one can be opened without pressing Next through the rest.
 *
 * **One head for every stepped flow.** Connecting a source (`ConnectFlow.tsx`) and installing a
 * template (`WizardSteps.tsx`) both draw their progress here, so a person who has met one knows the
 * other, and the thumb-tall buttons and the announcement of the current step are written once. It owns
 * no state: the flow says which step is current and is told when another is chosen.
 *
 * Task ids: M11.9.4, M27.11.9, M27.15.68
 */

import { cn } from "../../lib/utils";

export const STEPS_LABEL = "Steps";
export const FLAGGED = "The test sent you back here";

export function stepOf(index: number, total: number): string {
  return `Step ${index + 1} of ${total}`;
}

/** One step as the head needs it. */
export interface ProgressStep {
  readonly key: string;
  readonly title: string;
}

export function StepProgress({
  steps,
  at,
  onAt,
  flagged,
}: {
  readonly steps: readonly ProgressStep[];
  /** The index of the step shown. */
  readonly at: number;
  readonly onAt: (index: number) => void;
  /** The keys of the steps a test sent the person back to. */
  readonly flagged?: ReadonlySet<string> | undefined;
}) {
  const percent = Math.round(((at + 1) / Math.max(steps.length, 1)) * 100);
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <p className="m-0 text-[12.5px] font-semibold text-ink" aria-live="polite">
          {stepOf(at, steps.length)}
        </p>
      </div>
      <div aria-hidden className="h-1.5 w-full overflow-hidden rounded-full bg-sunk">
        <div className="h-full rounded-full bg-brand" style={{ width: `${percent}%` }} />
      </div>
      <ol aria-label={STEPS_LABEL} className="m-0 flex list-none flex-wrap gap-1.5 p-0">
        {steps.map((one, position) => {
          const current = position === at;
          const sentBack = flagged?.has(one.key) === true;
          return (
            <li key={one.key}>
              <button
                type="button"
                aria-current={current ? "step" : undefined}
                aria-label={`${stepOf(position, steps.length)}: ${one.title}${sentBack ? `. ${FLAGGED}` : ""}`}
                title={one.title}
                className={cn(
                  "inline-flex size-11 items-center justify-center rounded-full border text-[12px] font-semibold sm:size-7",
                  current ? "border-brand bg-brand text-brand-ink" : "border-line bg-panel text-body hover:bg-sunk",
                  sentBack && !current ? "border-warn bg-warn-wash text-warn" : null,
                )}
                onClick={() => {
                  onAt(position);
                }}
              >
                {position + 1}
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
