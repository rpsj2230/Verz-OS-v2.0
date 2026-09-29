/**
 * Connecting a source one screen at a time: "Step 2 of 6", a picture of the screen the step
 * happens on, what to press there in words, a link to that exact page where the vendor has one,
 * the values this screen collects, and Back and Next.
 *
 * **One component for every connector, driven by the API's steps.** Each source's steps, their
 * words, their pictures and their links are served by the API (`brain.ops.connect_steps`), so a
 * vendor renaming a menu is mended once on the server and every flow here draws it the same way.
 * A flow's page supplies only what each screen collects, as a panel per step key.
 *
 * **Every panel stays mounted, and only the current one is shown.** A secret typed on step 3 is
 * held by its own field (`ui/secret-field.tsx`), never by React, so a field that unmounted on Next
 * would lose it and Back would find it empty. Hidden panels keep their fields; closing the dialog
 * is what lets them go.
 *
 * **Any step can be opened from the list at the top**, because a returning administrator, or a
 * test that sends somebody back to one step, should not have to press Next through the rest. A step
 * a test flagged is marked there.
 *
 * Task ids: M11.9.4, M27.11.9
 */

import { ArrowLeft, ArrowRight, ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import type { components } from "../../api/schema";
import { cn } from "../../lib/utils";
import { Button, buttonVariants } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";
import { sketchMarks, StepSketch } from "./StepSketch";

export type FlowStep = components["schemas"]["GuideStepView"];

export const BACK = "Back";
export const NEXT = "Next";
export const STEPS_LABEL = "Steps";
export const FLAGGED = "The test sent you back here";

export function stepOf(index: number, total: number): string {
  return `Step ${index + 1} of ${total}`;
}

/** The index of the step with this key, or the first when none has it. */
export function indexOf(steps: readonly FlowStep[], key: string): number {
  const found = steps.findIndex((one) => one.key === key);
  return found < 0 ? 0 : found;
}

/** The picture's marks in words, numbered as the picture numbers them. */
function Marks({ step }: { readonly step: FlowStep }) {
  const marks = sketchMarks(step.sketch);
  if (marks.length === 0) {
    return null;
  }
  return (
    <ol aria-label="What the picture marks" className="m-0 flex list-none flex-wrap gap-x-3 gap-y-1 p-0 text-[12px] text-dim">
      {marks.map((one, index) => (
        <li key={`${one} ${index}`} className="flex items-center gap-1.5">
          <span aria-hidden className="inline-flex size-4 items-center justify-center rounded-full bg-acc-text text-[10px] font-bold text-panel">
            {index + 1}
          </span>
          <span>{one}</span>
        </li>
      ))}
    </ol>
  );
}

/** A step's picture with its marks under it, at any size. */
export function StepPicture({ step, className }: { readonly step: FlowStep; readonly className?: string | undefined }) {
  return (
    <figure className={cn("m-0 flex min-w-0 flex-col gap-2", className)}>
      <StepSketch sketch={step.sketch} className="rounded-lg" />
      <figcaption>
        <Marks step={step} />
      </figcaption>
    </figure>
  );
}

export function ConnectFlow({
  steps,
  at,
  onAt,
  panels,
  shared,
  flagged,
  onNext,
}: {
  readonly steps: readonly FlowStep[];
  /** The index of the step shown. */
  readonly at: number;
  readonly onAt: (index: number) => void;
  /** What each screen collects, by step key. Every panel stays mounted; see the module note. */
  readonly panels: Readonly<Record<string, ReactNode>>;
  /** Fields more than one screen shows, drawn above the panels and hidden by their own owner. */
  readonly shared?: ReactNode;
  /** The keys of the steps a test sent the person back to. */
  readonly flagged?: ReadonlySet<string> | undefined;
  /** Called before moving on from a step, with its key, so a flow can act on what was typed. */
  readonly onNext?: ((key: string) => void) | undefined;
}) {
  const index = Math.min(Math.max(at, 0), Math.max(steps.length - 1, 0));
  const step = steps[index];
  if (step === undefined) {
    return null;
  }
  const headingId = `flow-step-${step.key}`;
  const percent = Math.round(((index + 1) / steps.length) * 100);
  return (
    <div data-slot="connect-flow" className="flex min-w-0 flex-col gap-4">
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <p className="m-0 text-[12.5px] font-semibold text-ink" aria-live="polite">
            {stepOf(index, steps.length)}
          </p>
        </div>
        <div aria-hidden className="h-1.5 w-full overflow-hidden rounded-full bg-sunk">
          <div className="h-full rounded-full bg-brand" style={{ width: `${percent}%` }} />
        </div>
        <ol aria-label={STEPS_LABEL} className="m-0 flex list-none flex-wrap gap-1.5 p-0">
          {steps.map((one, position) => {
            const current = position === index;
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

      <section aria-labelledby={headingId} className="[display:grid] min-w-0 grid-cols-[minmax(0,1fr)] items-start gap-4 md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <StepPicture step={step} />
        <div className="flex min-w-0 flex-col gap-3">
          <h3 id={headingId} className="m-0 text-base font-semibold text-ink">
            {step.title}
          </h3>
          {flagged?.has(step.key) === true ? <p className="m-0 text-[12.5px] font-medium text-warn">{FLAGGED}.</p> : null}
          <p className="m-0 text-[13px] leading-relaxed text-body">{step.text}</p>
          {step.link === "" ? null : (
            <a
              href={step.link}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(buttonVariants({ variant: "outline" }), "min-h-11 self-start sm:min-h-9")}
            >
              {step.link_label}
              <ExternalLink aria-hidden />
            </a>
          )}
          {shared}
          {steps.map((one) => (
            <div key={one.key} data-panel={one.key} hidden={one.key !== step.key} className="min-w-0">
              {panels[one.key] ?? null}
            </div>
          ))}
        </div>
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
              onNext?.(step.key);
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

/** The dialog a flow opens in: wide enough for the picture beside the words, and a sheet on a phone. */
export function FlowDialog({
  title,
  description,
  children,
  onClose,
}: {
  readonly title: string;
  readonly description: string;
  readonly children: ReactNode;
  readonly onClose: () => void;
}) {
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogContent
        data-slot="flow-dialog"
        className="max-h-[calc(100dvh-1rem)] max-w-[calc(100%-1rem)] grid-cols-[minmax(0,1fr)] gap-4 overflow-x-hidden overflow-y-auto p-4 sm:max-h-[calc(100dvh-4rem)] sm:max-w-4xl sm:p-6"
      >
        <DialogHeader className="pr-10">
          <DialogTitle className="text-base font-semibold">{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}
