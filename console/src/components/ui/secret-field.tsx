/**
 * A field a credential is typed into once and never read back: an API key, a signing secret, a
 * source's password.
 *
 * Written here rather than copied, from the pattern `ConnectSource.tsx`, `pages/Notifications.tsx`
 * and `pages/Webhooks.tsx` each repeat by hand today (5.5 of the console plan), for M27.8.7's rule
 * that a credential is written once and never read back and rule R17 (`ops/credentials.py`).
 *
 * **The value is never in React.** The input is uncontrolled: what is typed lives in the element and
 * nowhere else, and `take()` on the handle from `useSecret` returns it and empties the field in the
 * same call, so the moment a page has the value in hand is the moment the field stops holding it.
 * Rejected: a controlled input, which is what every other field here is and what the three pages do
 * now. A controlled value is a copy in component state, visible to anything that can read the tree,
 * kept until somebody remembers to clear it, and written back into the element's `value` attribute
 * on every render, so a serialised page carries the key. None of that is a leak on its own and all
 * of it is a second place the credential is.
 *
 * **Never prefilled and never echoed.** The component accepts no value and no default value, so a
 * page cannot hand a stored secret back to it, and it has no reveal button and no copy button. When
 * the server says a value is stored, the field is empty and one fixed sentence says so; the sentence
 * is the same whatever is stored, so it carries neither the length nor the last four characters.
 * `tests/ui-controls.test.tsx` holds the exact list of what the component can be told.
 *
 * **A text field, not a password field.** `scripts/check-boundaries.mjs` refuses a password input
 * anywhere in the console, for the reason written there, so the field is `type="text"` with
 * autocomplete, spelling and capitalisation off, as the three pages already do. What that costs is
 * that the characters are visible while they are typed, which is the trade those pages already made.
 *
 * Task ids: M27.10.2
 */

import { useId, useMemo, useRef, type RefObject } from "react";
import { cn } from "../../lib/utils";
import { Input } from "./input";
import { Label } from "./label";

/** The rule, in words, for whoever is tempted to add a "show" button. */
export const A_SECRET_IS_WRITTEN_ONCE_AND_NEVER_READ_BACK =
  "A credential typed into the console is sent once and kept by nobody here: not in component " +
  "state, not in an attribute, not in a sentence about it. The server stores it and never returns " +
  "it, so there is nothing to show, and a field that could show one would be the place it leaked.";

/** What the field says when the server reports a value stored. The same whatever is stored. */
export const SECRET_STORED = "A value is stored. It is never shown, and typing here replaces it.";

/** What the field says when nothing is stored. */
export const SECRET_NOT_STORED = "Nothing is stored yet.";

export interface SecretHandle {
  readonly ref: RefObject<HTMLInputElement | null>;
  /** The value typed, with the field emptied in the same call. Empty when nothing was typed. */
  take(): string;
}

export function useSecret(): SecretHandle {
  const ref = useRef<HTMLInputElement | null>(null);
  return useMemo(
    () => ({
      ref,
      take() {
        const input = ref.current;
        if (input === null) {
          return "";
        }
        const value = input.value;
        input.value = "";
        // So `onPresenceChange` hears that the field is empty again, as it would from typing.
        input.dispatchEvent(new Event("input", { bubbles: true }));
        return value;
      },
    }),
    [],
  );
}

function SecretField({
  secret,
  label,
  stored,
  description,
  disabled,
  invalid,
  describedBy,
  onPresenceChange,
  className,
}: {
  /** The handle from `useSecret`, which is the only way to read what was typed. */
  secret: SecretHandle;
  label: string;
  /** Whether the server reports a value already stored. It never says what the value is. */
  stored: boolean;
  description?: string;
  disabled?: boolean;
  invalid?: boolean;
  /** The id of a problem drawn beside the field, when there is one. */
  describedBy?: string;
  /** Whether anything is typed, for a submit button, without the value leaving the field. */
  onPresenceChange?: (present: boolean) => void;
  className?: string;
}) {
  const id = useId();
  const statusId = `${id}-status`;
  const descriptionId = `${id}-description`;
  const described = [statusId, description === undefined ? null : descriptionId, describedBy ?? null]
    .filter((one): one is string => one !== null)
    .join(" ");
  return (
    <div data-slot="secret-field" className={cn("flex flex-col gap-2", className)}>
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        ref={secret.ref}
        type="text"
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        disabled={disabled}
        aria-invalid={invalid}
        aria-describedby={described}
        onInput={(event) => {
          onPresenceChange?.(event.currentTarget.value !== "");
        }}
      />
      <p id={statusId} className="m-0 text-sm text-muted-foreground">
        {stored ? SECRET_STORED : SECRET_NOT_STORED}
      </p>
      {description === undefined ? null : (
        <p id={descriptionId} className="m-0 text-sm text-muted-foreground">
          {description}
        </p>
      )}
    </div>
  );
}

export { SecretField };
