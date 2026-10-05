/**
 * Add work email, on the page of a person the staff list does not name (M1.10.4): the address is
 * bound to them, and the staff list's own person for it, when there is one, is joined into them.
 *
 * **Duplicates are found by address and never by name** (`brain.identity.work_email`). The person
 * made by hand before the list existed, the first administrator above all, has no address, so the
 * sync made a second person for theirs; typing it here is how the two become one. The API decides
 * what happens and says so in a sentence: bound, joined, or a question. **When the list's person has
 * signed in or somebody granted them something, the API writes nothing and asks**, and the page puts
 * that question in a confirmation; confirming sends the same request again saying so.
 *
 * Offered only when the API says this reader may (`may_add_work_email`), and the address is checked
 * for a shape before anything is sent.
 *
 * Task ids: M1.10.4
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, Drawer, FailureState } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Field } from "../access/formParts";
import { workEmailApiPath } from "./peopleQuery";

export const ADD_WORK_EMAIL = "Add work email";
export const WORK_EMAIL_TITLE = "Add their work email";
export const WORK_EMAIL_DESCRIPTION =
  "The staff list finds this person by it. If the list has already made a person for this email, the two are joined into this one.";
export const WORK_EMAIL_LABEL = "Work email";
export const WORK_EMAIL_HINT = "The address the staff list has for them, like name@company.example.";
export const WORK_EMAIL_BLANK = "Type their work email, like name@company.example.";
export const JOIN_QUESTION = "Join the staff list's person into this one?";
export const JOIN = "Join them";
export const NOT_NOW = "Not now";

const WORK_EMAIL_FORM = "work-email";

/** A shape a mailbox could have: something, an at sign, a domain with a dot. The API checks again. */
export function looksLikeAnAddress(typed: string): boolean {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(typed.trim());
}

interface Added {
  readonly outcome: string;
  readonly written: boolean;
  readonly told: string;
}

function readAdded(payload: unknown): Added | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Partial<Added>;
  return typeof body.outcome === "string" && typeof body.written === "boolean" && typeof body.told === "string"
    ? { outcome: body.outcome, written: body.written, told: body.told }
    : null;
}

export function WorkEmail({
  principalId,
  onDone,
}: {
  readonly principalId: string;
  /** What the API said, and whether it wrote. The page keeps the sentence across its reload. */
  readonly onDone: (told: string, written: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [address, setAddress] = useState("");
  const [blank, setBlank] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [asking, setAsking] = useState<string | null>(null);

  const send = (confirm: boolean) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(workEmailApiPath(principalId), {
        method: "POST",
        body: { address: address.trim(), confirm },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      const added = readAdded(result.data);
      if (added !== null && added.outcome === "ask") {
        setOpen(false);
        setAsking(added.told);
        return;
      }
      setOpen(false);
      setAsking(null);
      onDone(added?.told ?? "", added?.written === true);
    })();
  };

  const onSend = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const empty = !looksLikeAnAddress(address);
    setBlank(empty);
    if (empty) {
      return;
    }
    send(false);
  };

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setOpen(true);
          }}
        >
          {ADD_WORK_EMAIL}
        </Button>
      </div>
      <Drawer
        open={open}
        onOpenChange={(next) => {
          if (!next && !busy) {
            setOpen(false);
          }
        }}
        title={WORK_EMAIL_TITLE}
        description={WORK_EMAIL_DESCRIPTION}
        footer={
          <>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setOpen(false);
              }}
            >
              {NOT_NOW}
            </Button>
            <Button type="submit" form={WORK_EMAIL_FORM} disabled={busy}>
              {ADD_WORK_EMAIL}
            </Button>
          </>
        }
      >
        <form id={WORK_EMAIL_FORM} aria-label={WORK_EMAIL_TITLE} className="flex min-w-0 flex-col gap-4" noValidate onSubmit={onSend}>
          {failure === null ? null : <FailureState failure={failure} />}
          <Field
            label={WORK_EMAIL_LABEL}
            hint={WORK_EMAIL_HINT}
            problem={blank ? WORK_EMAIL_BLANK : null}
            apiProblems={failure?.problems ?? []}
            names={["address"]}
          >
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                name="address"
                type="email"
                autoComplete="off"
                aria-describedby={describedBy === "" ? undefined : describedBy}
                aria-invalid={invalid || undefined}
                value={address}
                onChange={(event) => {
                  setAddress(event.target.value);
                }}
              />
            )}
          </Field>
        </form>
      </Drawer>
      <ConfirmDialog
        open={asking !== null}
        question={JOIN_QUESTION}
        consequence={asking ?? ""}
        confirmLabel={JOIN}
        cancelLabel={NOT_NOW}
        busy={busy}
        onConfirm={() => {
          send(true);
        }}
        onCancel={() => {
          setAsking(null);
        }}
      />
    </div>
  );
}
