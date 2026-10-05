/**
 * The Settings row "Send the evening digest to": the conversations each connected channel offers,
 * chosen from a list and never typed, off until chosen, and why the digest has stopped when it has.
 *
 * Nothing here decides what may be chosen: the API lists what each channel offers now and refuses a
 * choice that is not on that list, and asks for the Settings screen's own authority first.
 *
 * Task ids: M38.3.3.1, M38.3.3.4
 */

import { useId, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, FailureState, LoadingState, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import {
  CHOOSE,
  chooseConsequence,
  chosenBody,
  choiceValue,
  currentValue,
  DESTINATION_NOT_SAVED,
  DESTINATION_SAVED,
  DIGEST_DESTINATION_API_PATH,
  KEEP_DESTINATION,
  NOTHING_TO_CHOOSE,
  OFF_LABEL,
  OFF_VALUE,
  READING_DESTINATION,
  readDestination,
  UNREADABLE_DESTINATION,
  type DestinationBody,
} from "../digestDestinationQuery";

function DestinationForm({ start, label }: { readonly start: DestinationBody; readonly label: string }) {
  const [body, setBody] = useState(start);
  const [value, setValue] = useState(currentValue(start));
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [told, setTold] = useState("");
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const id = useId();
  const offered = body.offers.some((offer) => offer.conversations.length > 0);

  const save = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(DIGEST_DESTINATION_API_PATH, { method: "PUT", body: chosenBody(value) });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      const next = readDestination(result.data);
      if (next !== null) {
        setBody(next);
        setValue(currentValue(next));
        setTold(DESTINATION_SAVED);
      }
    })();
  };

  return (
    <div className="flex min-w-0 flex-col gap-2">
      {body.stopped_because === "" ? null : <Note kind="not-yet">{body.stopped_because}</Note>}
      {offered ? null : <p className="m-0 text-[12.5px] leading-snug text-dim">{NOTHING_TO_CHOOSE}</p>}
      {body.offers
        .filter((offer) => offer.why_none !== "")
        .map((offer) => (
          <p key={offer.channel} className="m-0 text-[12.5px] leading-snug text-dim">
            {offer.channel}: {offer.why_none}
          </p>
        ))}
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
        <Label htmlFor={id} className="sr-only">
          {label}
        </Label>
        <select
          id={id}
          name="digest_destination"
          className="h-9 rounded-md border border-input bg-transparent px-2.5 text-sm text-ink sm:max-w-md"
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
          }}
        >
          <option value={OFF_VALUE}>{OFF_LABEL}</option>
          {body.offers.map((offer) => (
            <optgroup key={offer.channel} label={offer.channel}>
              {offer.conversations.map((one) => (
                <option key={one.conversation} value={choiceValue(one.channel, one.conversation)}>
                  {one.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <Button
          type="button"
          size="sm"
          className="min-h-11 sm:min-h-8"
          disabled={busy || value === currentValue(body)}
          onClick={() => {
            setFailure(null);
            setTold("");
            setAsking(true);
          }}
        >
          {CHOOSE}
        </Button>
      </div>
      {told === "" ? null : (
        <div role="status">
          <Note kind="done">{told}</Note>
        </div>
      )}
      {failure === null ? null : <FailureState failure={failure} title={DESTINATION_NOT_SAVED} />}
      <ConfirmDialog
        open={asking}
        question={`Send the evening digest to ${value === OFF_VALUE ? "nowhere" : "this conversation"}?`}
        consequence={chooseConsequence(body, value)}
        confirmLabel={CHOOSE}
        cancelLabel={KEEP_DESTINATION}
        busy={busy}
        onConfirm={save}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </div>
  );
}

/** The row's control, read from the API when the row is drawn. */
export function DigestDestination({ label }: { readonly label: string }) {
  const answer = useResource<unknown>(DIGEST_DESTINATION_API_PATH);
  if (answer.busy) {
    return <LoadingState label={READING_DESTINATION} />;
  }
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  const body = readDestination(answer.data);
  return body === null ? <Note>{UNREADABLE_DESTINATION}</Note> : <DestinationForm start={body} label={label} />;
}
