/**
 * A checkbox with three states: checked, not checked, and some of a set checked.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike, with the focus
 * ring changed as `button.tsx` explains, and one defect fixed in a different way from the spike's.
 *
 * **"Some selected" draws a dash and never a tick.** shadcn/ui renders the same tick for
 * `checked="indeterminate"` as for `checked`, so a header checkbox over a partly selected list says
 * the whole list is selected, and an action taken on that belief reaches rows the person did not
 * choose. The spike hid the tick with a class for the indeterminate state; that is correct in a
 * browser and invisible to every test here, because jsdom applies no stylesheet. So the choice is
 * made in the markup instead: the state is followed here, controlled or not, and only the icon that
 * matches it is rendered. `tests/ui-controls.test.tsx` asserts which icon is in the document.
 *
 * Task ids: M27.10.2
 */

import { CheckIcon, MinusIcon } from "lucide-react";
import { Checkbox as CheckboxPrimitive } from "radix-ui";
import { useState, type ComponentProps } from "react";
import { cn } from "../../lib/utils";

type CheckedState = boolean | "indeterminate";

function Checkbox({
  className,
  checked,
  defaultChecked,
  onCheckedChange,
  ...props
}: ComponentProps<typeof CheckboxPrimitive.Root>) {
  const [uncontrolled, setUncontrolled] = useState<CheckedState>(defaultChecked ?? false);
  const state = checked ?? uncontrolled;
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      checked={state}
      onCheckedChange={(next) => {
        if (checked === undefined) {
          setUncontrolled(next);
        }
        onCheckedChange?.(next);
      }}
      className={cn(
        "peer relative flex size-4 shrink-0 items-center justify-center rounded-[4px] border border-input shadow-xs transition-shadow outline-hidden after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive data-checked:border-primary data-checked:bg-primary data-checked:text-primary-foreground data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="[display:grid] place-content-center text-current transition-none [&>svg]:size-3.5"
      >
        {state === "indeterminate" ? <MinusIcon /> : <CheckIcon />}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
