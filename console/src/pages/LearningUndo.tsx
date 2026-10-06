/**
 * Undo one learning a weekly digest named: one page, one button, and what the undo did.
 *
 * **Opening the link undoes nothing; pressing Undo and confirming does.** A chat unfurls a link it
 * is sent, and a mail scanner follows one, so an undo that ran on opening would be pressed by
 * software before the person read the message. The address is the memory's id, and the POST is sent
 * only from the kit's confirmation, which says what undoing does, as Forget on My workspace is: it
 * switches off something in use, which `tests/destructive-confirmed.test.ts` holds to a confirmation.
 *
 * **It opens for every signed-in person.** The API's route asks for no grant, only that the memory
 * was formed from the reader's own words (`learningUndoQuery.ts`), so somebody who never held the
 * member grant can undo what the system learnt from them. A 404 is the API saying the memory is not
 * theirs or not there, alike, and the page says no more than that.
 *
 * Imported statically rather than split: it mounts neither heavy library and no stylesheet.
 *
 * Task ids: M16.5.1
 */

import { useCallback, useState } from "react";
import { useParams } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { ConfirmDialog } from "../components/kit";
import { Button } from "../components/ui/button";
import { FailureNotice } from "../ui/FailureNotice";
import { LEARNING_UNDO_API_PATH, undoBody } from "./learningUndoQuery";
import { readChanged } from "./myWorkspaceQuery";

export const UNDO_HEADING = "Undo a learning";
export const UNDO_LEDE =
  "Your weekly digest named this as something the system learnt from your conversations. " +
  "Undoing it marks it so it stops being used in your answers at once; the record that it was " +
  "learnt stays, and if it replaced something earlier, the earlier one is used again.";
export const UNDO_LABEL = "Undo it";
export const KEEP_IT = "Keep it";
export const UNDO_QUESTION = "Undo this learning?";
export const UNDO_CONSEQUENCE =
  "It stops being used in your answers at once. The record that it was learnt stays, and if it " +
  "replaced something earlier, the earlier one is used again.";
export const NOT_UNDONE_TITLE = "This was not undone";

export function LearningUndo() {
  const { memoryId = "" } = useParams();
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [said, setSaid] = useState("");
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const undo = useCallback(() => {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(LEARNING_UNDO_API_PATH, {
        method: "POST",
        body: undoBody(memoryId),
      });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setSaid(readChanged(result.data).told);
    })();
  }, [memoryId]);

  return (
    <article className="page">
      <h1>{UNDO_HEADING}</h1>
      <p className="lede">{UNDO_LEDE}</p>
      <p>
        Memory <code>{memoryId}</code>
      </p>
      {said === "" ? (
        <Button
          type="button"
          onClick={() => {
            setAsking(true);
          }}
          disabled={busy || memoryId === ""}
        >
          {UNDO_LABEL}
        </Button>
      ) : (
        <p className="note" role="status">
          {said}
        </p>
      )}
      {failure === null ? null : <FailureNotice failure={failure} title={NOT_UNDONE_TITLE} />}
      <ConfirmDialog
        open={asking}
        question={UNDO_QUESTION}
        consequence={UNDO_CONSEQUENCE}
        confirmLabel={UNDO_LABEL}
        cancelLabel={KEEP_IT}
        busy={busy}
        onConfirm={undo}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </article>
  );
}
