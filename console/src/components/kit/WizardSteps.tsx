/**
 * A short flow one screen at a time: "Step 2 of 4", what this step asks, Back and Next, and the last
 * step as the place to check it and do it.
 *
 * **The flow owns what was typed and this owns the walking.** The page keeps its values (in
 * `useFlowDraft`, so they survive leaving the page) and hands this each step's body, so a step can be
 * any form the page already had. The head is `StepProgress.tsx`, the one `ConnectFlow.tsx` draws too,
 * and any step can be opened from it, because somebody coming back to change one answer should not
 * press Next through the rest.
 *
 * **Only the current step is mounted.** Unlike `ConnectFlow`, whose steps hold secret fields that must
 * outlive a step change, a step here holds plain values the page keeps itself, so an unmounted step
 * loses nothing and a screen reader meets one step at a time.
 *
 * **The last step has no Next.** It ends in the page's own act, behind its own confirmation, because
 * pressing Next is not consent to a write and this must not become the way a write skips its dialog.
 *
 * Task ids: M27.15.68
 */

import { ArrowLeft, ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../ui/button";
import { StepProgress } from "./StepProgress";

export const BACK = "Back";
export const NEXT = "Next";

export interface WizardStep {
  readonly key: string;
  readonly title: string;
  /** One sentence under the title saying what the step is for. */
  readonly hint?: string | undefined;
  readonly body: ReactNode;
}

export function WizardSteps({
  steps,
  at,
  onAt,
}: {
  readonly steps: readonly WizardStep[];
  readonly at: number;
  readonly onAt: (index: number) => void;
}) {
  const index = Math.min(Math.max(at, 0), Math.max(steps.length - 1, 0));
  const step = steps[index];
  if (step === undefined) {
    return null;
  }
  const headingId = `wizard-step-${step.key}`;
  return (
    <div data-slot="wizard-steps" className="flex min-w-0 flex-col gap-4">
      <StepProgress steps={steps} at={index} onAt={onAt} />
      <section aria-labelledby={headingId} className="flex min-w-0 flex-col gap-3">
        <h3 id={headingId} className="m-0 text-base font-semibold text-ink">
          {step.title}
        </h3>
        {step.hint === undefined ? null : <p className="m-0 text-[13px] leading-relaxed text-body">{step.hint}</p>}
        {step.body}
      </section>
      <div className="flex items-center justify-between gap-2 border-t border-line pt-3">
        <Button
          type="button"
          variant="outline"
          className="min-h-11 sm:min-h-9"
          disabled={index === 0}
          onClick={() => {
            onAt(index - 1);
          }}
        >
          <ArrowLeft aria-hidden />
          {BACK}
        </Button>
        {index === steps.length - 1 ? null : (
          <Button
            type="button"
            className="min-h-11 sm:min-h-9"
            onClick={() => {
              onAt(index + 1);
            }}
          >
            {NEXT}
            <ArrowRight aria-hidden />
          </Button>
        )}
      </div>
    </div>
  );
}
