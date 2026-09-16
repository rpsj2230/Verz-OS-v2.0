/**
 * A destructive control's second step: what will happen, to whom, and a way out.
 *
 * `docs/admin-console.md` requires a destructive action to be confirmed and to say what will
 * happen and to what. The Sessions and Sign-in links screens each have one, and a confirmation
 * written twice is two confirmations that drift, so it is written once here.
 *
 * **In the page, not a modal.** A modal needs a focus trap, an inert background and a portal,
 * and every one of those is a place for a keyboard user to get lost. The panel replaces the
 * control that opened it, focus moves to the choice that changes nothing, and Escape is that
 * choice too.
 *
 * **The consequence is a sentence somebody else wrote.** The screens pass the API's own sentence
 * about what the act does, so the words a person agrees to are the words of the system that will
 * do it rather than this console's paraphrase of them.
 *
 * **It decides nothing.** Confirming sends the request; the API refuses or accepts it whatever
 * this panel believed about the row.
 *
 * **Some confirmations are a list of facts rather than one sentence**, and `details` is where they
 * go, between the consequence and the warning. Installing an automation asks a person to agree to
 * who it runs as, when, and what it reaches, and a sentence holding all four is one nobody reads.
 * Optional, so every confirmation that is one sentence stays exactly as it was.
 *
 * Task ids: M27.7.10, M27.7.11
 */

import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface ConfirmActionProps {
  /** The question, naming the person and the thing: "End Wei Ling's session from 09:14?" */
  readonly question: string;
  /** What happens if they go ahead, in the API's words. */
  readonly consequence: string;
  /** The facts being agreed to, when one sentence cannot hold them. Drawn before the warning. */
  readonly details?: ReactNode;
  /** Anything further this particular case has to say, such as that it is their own. */
  readonly warning?: string;
  /** The button that does it, as a verb: "End session". */
  readonly confirmLabel: string;
  /** The button that changes nothing. */
  readonly cancelLabel: string;
  readonly busy: boolean;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}

export function ConfirmAction({
  question,
  consequence,
  details,
  warning,
  confirmLabel,
  cancelLabel,
  busy,
  onConfirm,
  onCancel,
}: ConfirmActionProps) {
  const keep = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // The choice that changes nothing takes focus, so a stray Enter keeps things as they are.
    keep.current?.focus();
  }, []);

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
    }
  }

  return (
    <section className="card confirm" role="group" aria-label={question} onKeyDown={onKeyDown}>
      <p className="confirm__question">
        <strong>{question}</strong>
      </p>
      <p>{consequence}</p>
      {details}
      {warning === undefined ? null : <p className="note">{warning}</p>}
      <div className="form-actions">
        <button type="button" className="button" ref={keep} onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </button>{" "}
        <button type="button" className="button" onClick={onConfirm} disabled={busy}>
          {confirmLabel}
        </button>
      </div>
    </section>
  );
}
