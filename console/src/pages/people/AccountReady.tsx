/**
 * The sentence an administrator passes on to somebody whose sign-in account the staff sync made, with
 * a way to copy it. The owner decided on 2026-09-29 (needs-rupash 115) that nobody is sent anything:
 * a person presses Forgot password on the sign-in page. So telling them is the administrator's, and
 * this is the sentence, as the API sends it (`brain.identity.staff_accounts.YOUR_ACCOUNT_IS_READY`),
 * never composed here.
 *
 * Drawn on People and on Staff sources, only when the API sends it: an install reading no staff list
 * makes no accounts and gets none.
 *
 * Task ids: M1.6.16
 */

import { useState } from "react";
import { SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";

export const ACCOUNT_READY_HEADING = "What to tell people";
export const ACCOUNT_READY_LEDE =
  "The staff sync makes each active person's account and sends nobody anything. Pass this on, by chat or by email.";
export const COPY = "Copy";
export const COPIED = "Copied";
export const NOT_COPIED = "Your browser did not allow copying. Select the sentence and copy it.";

/** Copy a text to the clipboard, answering whether the browser allowed it. */
async function copied(text: string): Promise<boolean> {
  const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;
  if (clipboard === undefined) {
    return false;
  }
  try {
    await clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** The sentence and a Copy button, with no card around it, for a page that already has one. */
export function CopySentence({ sentence }: { readonly sentence: string }) {
  const [told, setTold] = useState<"" | "copied" | "refused">("");
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex min-w-0 flex-wrap items-start gap-3">
        <blockquote className="m-0 min-w-0 flex-1 border-l-2 border-line pl-3 text-[13px]">{sentence}</blockquote>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 sm:min-h-8"
          onClick={() => {
            void copied(sentence).then((ok) => {
              setTold(ok ? "copied" : "refused");
            });
          }}
        >
          {told === "copied" ? COPIED : COPY}
        </Button>
      </div>
      {told === "refused" ? <p className="m-0 text-[12px] text-dim">{NOT_COPIED}</p> : null}
    </div>
  );
}

/** The sentence in its own card, for People. */
export function AccountReady({ sentence }: { readonly sentence: string }) {
  return (
    <SectionCard title={ACCOUNT_READY_HEADING} lede={ACCOUNT_READY_LEDE}>
      <CopySentence sentence={sentence} />
    </SectionCard>
  );
}
