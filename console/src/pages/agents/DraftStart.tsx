/**
 * Starting a draft: of a new agent from scratch or from a template, or of an agent as it is now,
 * each confirmed and each landing on the draft's own page.
 *
 * **One hook for the three ways in**, because New agent offers two and an agent's page offers the
 * third, and all three say the same thing before anything is made: a draft is the reader's alone,
 * nothing in it is live, and a publish is a separate, checked act. The write is sent only from the
 * kit's `ConfirmDialog`, which `tests/destructive-confirmed.test.ts` follows to its `onConfirm`, and
 * a refusal is drawn in the API's own words.
 *
 * Task ids: M27.11.6
 */

import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog } from "../../components/kit";
import { FailureNotice } from "../../ui/FailureNotice";
import {
  DRAFTS_API_PATH,
  EDIT_CONSEQUENCE,
  EDIT_QUESTION,
  KEEP_LABEL,
  START_CONSEQUENCE,
  START_SCRATCH_QUESTION,
  START_TEMPLATE_QUESTION,
  draftAddress,
  editAsDraftApiPath,
  readNotChanged,
  startedDraftId,
} from "./agentDraftsQuery";

/** What a draft starts from. */
export type DraftFrom =
  | { readonly kind: "scratch" }
  | { readonly kind: "template"; readonly templateId: string; readonly name: string }
  | { readonly kind: "agent"; readonly agentId: string; readonly name: string };

export const START_LABEL = "Start the draft";
export const NOT_STARTED = "No draft was started";

export interface DraftStart {
  /** Ask to start a draft from one of the three places. Nothing is sent until it is confirmed. */
  readonly begin: (from: DraftFrom) => void;
  readonly busy: boolean;
  /** The confirmation. Rendered once by the page. */
  readonly dialog: ReactNode;
  /** Why nothing was started, when it was not. Rendered once by the page. */
  readonly notice: ReactNode;
}

function question(from: DraftFrom): string {
  if (from.kind === "scratch") {
    return START_SCRATCH_QUESTION;
  }
  return from.kind === "template" ? START_TEMPLATE_QUESTION(from.name) : EDIT_QUESTION(from.name);
}

export function useDraftStart(): DraftStart {
  const navigate = useNavigate();
  const [chosen, setChosen] = useState<DraftFrom | null>(null);
  const [sending, setSending] = useState(false);
  const [refused, setRefused] = useState<{ readonly failure: ApiFailure; readonly sentence?: string } | null>(null);

  const confirm = () => {
    if (chosen === null) {
      return;
    }
    const from = chosen;
    setSending(true);
    void (async () => {
      const result =
        from.kind === "agent"
          ? await request<unknown>(editAsDraftApiPath(from.agentId), { method: "POST", body: {} })
          : await request<unknown>(DRAFTS_API_PATH, {
              method: "POST",
              body: from.kind === "template" ? { template_id: from.templateId } : {},
            });
      setSending(false);
      setChosen(null);
      if (result.ok) {
        const draftId = startedDraftId(result.data);
        if (draftId !== null) {
          navigate(draftAddress(draftId));
        }
        return;
      }
      const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
      setRefused(notChanged === null ? { failure: result.failure } : { failure: result.failure, sentence: notChanged.sentence });
    })();
  };

  const dialog = (
    <ConfirmDialog
      open={chosen !== null}
      question={chosen === null ? "" : question(chosen)}
      consequence={chosen?.kind === "agent" ? EDIT_CONSEQUENCE : START_CONSEQUENCE}
      confirmLabel={START_LABEL}
      cancelLabel={KEEP_LABEL}
      busy={sending}
      onConfirm={confirm}
      onCancel={() => {
        setChosen(null);
      }}
    />
  );

  const notice =
    refused === null ? null : (
      <FailureNotice
        failure={refused.failure}
        title={NOT_STARTED}
        {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
      />
    );

  return {
    begin: (from) => {
      setRefused(null);
      setChosen(from);
    },
    busy: sending,
    dialog,
    notice,
  };
}
