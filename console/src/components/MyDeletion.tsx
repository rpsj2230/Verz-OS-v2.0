/**
 * Asking for one's own data to be deleted, in My workspace (M40.4.2.3).
 *
 * The card first says what a deletion reaches, what only time removes and what is kept on purpose,
 * as the retention policy lists them, and only then offers the ask. **Asking deletes nothing**: it
 * records the ask for whoever holds the erasure authority, and the card says so before and after.
 * The ask is confirmed, because it is the first step to an irreversible erasure, and a confirmation
 * that keeps the choice that changes nothing in focus. A person with an ask waiting is shown it and
 * offered no second; the API shows when it is switched off by offering nothing.
 *
 * Task ids: M40.4.2.3
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { when } from "../pages/artifactsQuery";
import { MY_DELETION_API_PATH, type MyDeletion, type StoreLine } from "../pages/myDeletionQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { ConfirmAction } from "./ConfirmAction";

export const DELETION_CAPTION = "Ask for my data to be deleted";
export const ASK_DELETION_LABEL = "Ask for my data to be deleted";
export const KEEP_MY_DATA_LABEL = "Do not ask";
export const DELETION_QUESTION = "Ask for all of your data to be deleted?";
export const DELETION_CONSEQUENCE =
  "This sends your request to whoever holds the erasure authority. Nothing is deleted by asking. " +
  "When they file the erasure, it is carried out in the order listed here, it cannot be brought " +
  "back, and your account and sign-in are retired with the rest.";
export const READS_LABEL = "A deletion reaches";
export const ROTATES_LABEL = "Only time removes";
export const RETAINED_LABEL = "Kept on purpose";

function Lines({ label, stores }: { readonly label: string; readonly stores: readonly StoreLine[] }) {
  if (stores.length === 0) {
    return null;
  }
  return (
    <>
      <h3>{label}</h3>
      <ul aria-label={label}>
        {stores.map((one) => (
          <li key={one.store}>{one.holds}</li>
        ))}
      </ul>
    </>
  );
}

export function MyDeletionCard() {
  const [version, setVersion] = useState(0);
  const answer = useResource<MyDeletion>(MY_DELETION_API_PATH, version);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const ask = useCallback(() => {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<MyDeletion>(MY_DELETION_API_PATH, { method: "POST" });
      setBusy(false);
      setConfirming(false);
      if (result.ok) {
        setVersion((current) => current + 1);
        return;
      }
      setFailure(result.failure);
    })();
  }, []);

  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  if (answer.data === null) {
    return (
      <p className="note" role="status">
        Reading what a deletion would do.
      </p>
    );
  }
  const shown = answer.data;
  return (
    <section className="card">
      <h2>{DELETION_CAPTION}</h2>
      <p>{shown.told}</p>
      {shown.asked_at === null ? null : <p className="note">{`Asked ${when(shown.asked_at)}.`}</p>}
      {failure === null ? null : <FailureNotice failure={failure} />}
      <Lines label={READS_LABEL} stores={shown.route.reaches} />
      <Lines label={ROTATES_LABEL} stores={shown.route.rotates_out} />
      <Lines label={RETAINED_LABEL} stores={shown.route.retained} />
      {confirming ? (
        <ConfirmAction
          question={DELETION_QUESTION}
          consequence={DELETION_CONSEQUENCE}
          confirmLabel={ASK_DELETION_LABEL}
          cancelLabel={KEEP_MY_DATA_LABEL}
          busy={busy}
          onConfirm={ask}
          onCancel={() => {
            setConfirming(false);
          }}
        />
      ) : shown.may_ask ? (
        <button
          type="button"
          className="button"
          onClick={() => {
            setConfirming(true);
          }}
        >
          {ASK_DELETION_LABEL}
        </button>
      ) : null}
    </section>
  );
}
