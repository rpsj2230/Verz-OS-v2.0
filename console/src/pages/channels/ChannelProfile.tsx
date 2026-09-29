/**
 * The Profile view of one channel: its identifiers and write-only secret, the switch with them, and
 * a test message.
 *
 * **Every field says what it accepts before anything is sent.** An identifier is one unbroken line
 * of at most 500 characters, which is `brain.channel_routes.tenant_problems`' rule; the secret is
 * kept in the vault and never shown, and an empty secret field keeps the one held; the test's
 * destination is in the vendor's own terms. A blank identifier and a blank destination are said
 * beside their fields before a confirmation opens, and whatever the API still refuses is drawn
 * beside the field it names.
 *
 * **The secret is never in React.** It is typed into `ui/secret-field.tsx` and taken out of the
 * field, which empties it, only once the person has confirmed; the request body is the only place
 * it goes, for `ui/secret-field.A_SECRET_IS_WRITTEN_ONCE_AND_NEVER_READ_BACK`'s reason.
 *
 * **Saving is confirmed; a test message is not.** A save replaces the identifiers kept and the
 * secret in the vault, both recorded in the audit ledger, so it asks first. A test message is one
 * product sentence to one destination, sent once per record and destination, which ends and
 * replaces nothing (`tests/destructive-confirmed.test.ts` records why).
 *
 * Task ids: M27.13.1, M10.3.3, M10.2.1, M27.16.1
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { ConfirmDialog, Fact, FactList, NotOffered, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { SecretField, useSecret } from "../../components/ui/secret-field";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  TENANT_FORMAT,
  TEST_OUTCOMES,
  channelApiPath,
  setupBody,
  setupProblems,
  testApiPath,
  testProblems,
  type TestBody,
} from "../channelsQuery";
import { ACT_LABELS } from "./channelActions";
import type { ChannelRow } from "./channelRows";

export const SETUP_HEADING = "Set-up";
export const SETUP_LEDE = "The identifiers its vendor gave this install, and the secret that signs its requests.";
export const NO_IDENTIFIERS = "This channel takes no identifiers: its secret and its switch are all it needs.";
export const SECRET_LABEL = "Secret (write only)";
export const SECRET_FORMAT = "Kept in the vault and never shown again. Leave it empty to keep the secret held now.";
export const ENABLED_LABEL = "Switched on";
export const EVENTS_LABEL = "Vendor posts to";
export const EVENTS_FORMAT = "Give this address to the vendor, under this install's own web address.";
export const KEEP_LABEL = "Keep it as it is";
export const SAVE_CONSEQUENCE =
  "The identifiers below replace the ones kept, and a secret typed here replaces the one in the vault. Both are " +
  "recorded in the audit ledger, never the secret itself.";
export const NOT_SAVED = "The set-up was not saved";
export const SAVED = "The set-up is saved.";

export const TEST_HEADING = "Test message";
export const TEST_LEDE = "One short product sentence through the vendor, to prove this channel can send.";
export const TEST_TO_LABEL = "Send it to";
export const TEST_TO_FORMAT = "Where the vendor should deliver it, in the vendor's own terms: a chat, conversation or sender id.";
export const SAVE_FIRST = "Save the set-up first. A test message goes out through it.";
export const NOT_SENT = "The test message was not sent";
export const NOT_RECEIVED =
  "This release cannot receive or reply on this channel yet, so there is nothing to set up here.";

const SETUP_FORM = "channel-setup";
const TEST_FORM = "channel-test";

function readTold(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const told = (payload as { told?: unknown }).told;
  return typeof told === "string" ? told : "";
}

/** The set-up form: its identifiers, its write-only secret and its switch. The connect flow's last screen too. */
export function SetUp({ row, onChanged }: { readonly row: ChannelRow; readonly onChanged: (told: string) => void }) {
  const [values, setValues] = useState<Record<string, string>>({ ...row.tenant });
  const [enabled, setEnabled] = useState(row.status === "on");
  const secret = useSecret();
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = setupProblems(row.tenant_fields, values);
    setBlank(found);
    setAsking(found.length === 0);
  };

  const sendSetUp = () => {
    // Read from the field only now, and the field emptied in the same call: the secret is sent once
    // and kept nowhere here.
    const body = setupBody(enabled, row.tenant_fields, values, secret.take());
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(channelApiPath(row.channel), { method: "PUT", body });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onChanged(SAVED);
    })();
  };

  return (
    <SectionCard title={SETUP_HEADING} lede={SETUP_LEDE}>
      <form
        id={SETUP_FORM}
        aria-label={`Set up ${row.label}`}
        className="flex min-w-0 flex-col gap-4"
        noValidate
        autoComplete="off"
        onSubmit={ask}
      >
        {row.tenant_fields.length === 0 ? <p className="m-0 text-[12.5px] text-dim">{NO_IDENTIFIERS}</p> : null}
        {row.tenant_fields.map((field) => (
          <div key={field} className="flex min-w-0 flex-col gap-2">
            <Label htmlFor={`${SETUP_FORM}-${field}`}>{field}</Label>
            <Input
              id={`${SETUP_FORM}-${field}`}
              name={field}
              value={values[field] ?? ""}
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
              {...problemAttributes(problems, SETUP_FORM, [field, `tenant.${field}`])}
              onChange={(event) => {
                setValues({ ...values, [field]: event.target.value });
              }}
            />
            <p className="m-0 text-[12.5px] leading-snug text-dim">{TENANT_FORMAT}</p>
            <FieldProblems problems={problems} form={SETUP_FORM} names={[field, `tenant.${field}`]} />
          </div>
        ))}
        <SecretField
          secret={secret}
          label={SECRET_LABEL}
          stored={row.secret === "held"}
          description={SECRET_FORMAT}
          disabled={busy}
        />
        <FieldProblems problems={problems} form={SETUP_FORM} names="secret" />
        <label className="flex min-h-11 items-center gap-2 text-[13px] text-ink sm:min-h-8">
          <input
            type="checkbox"
            name="enabled"
            className="size-4"
            checked={enabled}
            disabled={busy}
            onChange={(event) => {
              setEnabled(event.target.checked);
            }}
          />
          {ENABLED_LABEL}
        </label>
        <div>
          <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy || asking}>
            {ACT_LABELS.save}
          </Button>
        </div>
      </form>
      {failure === null ? null : (
        <div className="mt-3">
          <FailureNotice failure={failure} title={NOT_SAVED} fields={[...row.tenant_fields, "secret"]} />
        </div>
      )}
      <ConfirmDialog
        open={asking}
        question={`Save the set-up of ${row.label}?`}
        consequence={SAVE_CONSEQUENCE}
        confirmLabel={ACT_LABELS.save}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={sendSetUp}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </SectionCard>
  );
}

/** One product sentence through the vendor to one destination. The connect flow offers it once saved. */
export function TestMessage({ row }: { readonly row: ChannelRow }) {
  const [to, setTo] = useState("");
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];

  const send = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    setSaid(null);
    const found = testProblems(to);
    setBlank(found);
    if (found.length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<TestBody>(testApiPath(row.channel), { method: "POST", body: { to: to.trim() } });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setSaid(`${TEST_OUTCOMES[result.data.outcome] ?? result.data.outcome} ${readTold(result.data)}`.trim());
    })();
  };

  return (
    <SectionCard title={TEST_HEADING} lede={TEST_LEDE}>
      <form id={TEST_FORM} aria-label={`${ACT_LABELS.test} on ${row.label}`} className="flex min-w-0 flex-col gap-4" noValidate onSubmit={send}>
        <div className="flex min-w-0 flex-col gap-2">
          <Label htmlFor={`${TEST_FORM}-to`}>{TEST_TO_LABEL}</Label>
          <Input
            id={`${TEST_FORM}-to`}
            name="to"
            value={to}
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
            {...problemAttributes(problems, TEST_FORM, "to")}
            onChange={(event) => {
              setTo(event.target.value);
            }}
          />
          <p className="m-0 text-[12.5px] leading-snug text-dim">{TEST_TO_FORMAT}</p>
          <FieldProblems problems={problems} form={TEST_FORM} names="to" />
        </div>
        <div>
          <Button type="submit" variant="outline" className="min-h-11 sm:min-h-9" disabled={busy}>
            {ACT_LABELS.test}
          </Button>
        </div>
      </form>
      {said === null ? null : (
        <div role="status" className="mt-3">
          <Note>{said}</Note>
        </div>
      )}
      {failure === null ? null : (
        <div className="mt-3">
          <FailureNotice failure={failure} title={NOT_SENT} fields={["to"]} />
        </div>
      )}
    </SectionCard>
  );
}

export function ChannelProfile({ row, onChanged }: { readonly row: ChannelRow; readonly onChanged: (told: string) => void }) {
  if (!row.receives) {
    return <NotOffered>{NOT_RECEIVED}</NotOffered>;
  }
  return (
    <div data-slot="channel-profile" className="flex min-w-0 flex-col gap-4">
      <SectionCard title="Where it is reached">
        <FactList>
          <Fact label={EVENTS_LABEL}>
            <span className="font-mono text-[12px]">{row.events_path}</span>
            <p className="m-0 mt-1 text-[12px] text-dim">{EVENTS_FORMAT}</p>
          </Fact>
        </FactList>
      </SectionCard>
      <SetUp key={`${row.changed_at ?? "never"}-${row.status}`} row={row} onChanged={onChanged} />
      {row.status === "not_set_up" ? <Note>{SAVE_FIRST}</Note> : <TestMessage row={row} />}
    </div>
  );
}
