/**
 * The acts on one source that change something: connect, edit its settings, replace its key and
 * disconnect it, plus Connect Lark and the export, which change nothing.
 *
 * **Every write is sent from a confirmation.** Connecting is `components/ConnectSource.tsx`, which
 * first run uses too and which confirms in the API's words; editing, replacing a key and
 * disconnecting each open `kit/ConfirmDialog` with the sentence the API serves for that act, so the
 * words a person agrees to are the words of the system that does it. `tests/destructive-confirmed.
 * test.ts` follows each write here to its `onConfirm`.
 *
 * **Every form says what it accepts before it is sent.** Each setting carries the API's hint under
 * its field, and a blank one is said beside it in the API's own blank sentence before the
 * confirmation opens; the key field says what kind of key and that it is pasted as one piece.
 *
 * **A key is typed into `ui/secret-field.tsx` and never held by React.** It is taken out of the field
 * in the same call that empties it, at the moment the confirmed request is built, and the request
 * body is the only place it goes. See `pages/connectorsQuery.ts`'
 * `A_KEY_IS_SENT_ONCE_AND_KEPT_BY_NOBODY_HERE`.
 *
 * **An edit sends the settings and never a key.** The API connects the source again with them as
 * one change and leaves the key alone, which the confirmation says.
 *
 * Task ids: M27.11.9, M11.7.7, M11.2.6
 */

import { useId, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { ConnectLark } from "../../components/ConnectLark";
import { ConnectSource } from "../../components/ConnectSource";
import { ConfirmDialog, Drawer, Fact, FactList, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { SecretField, useSecret } from "../../components/ui/secret-field";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  disconnectApiPath,
  offered,
  readTold,
  type Connectable,
  type Connectors as ConnectorsBody,
} from "../connectorsQuery";
import { ACT_LABELS } from "./connectorActions";
import { editApiPath, exportApiPath, exportFileName, keyApiPath, type SettingValue } from "./connectorSources";

/** The drawers' and dialogs' own words. */
export const CONNECT_TITLE = "Connect a source";
export const CONNECT_DESCRIPTION = "Its settings are kept on this install and its key in the vault.";
export const WHICH_SOURCE = "Source to connect";
export const NOTHING_TO_CONNECT =
  "There is no source here you may connect. Connecting one needs the connector installation grant over it.";
export const EDIT_TITLE = "Edit settings";
export const EDIT_DESCRIPTION = "The source is connected again with these settings, as one change.";
export const KEY_TITLE = "Replace key";
export const KEY_DESCRIPTION = "A new key for this connection. Nothing else about it changes.";
export const LARK_DESCRIPTION = "Create the Lark app, test it, and switch on what it is for.";
export const NOT_EDITED = "The settings were not changed";
export const NOT_REPLACED = "The key was not replaced";
export const NOT_DISCONNECTED = "The source was not disconnected";
export const NOT_EXPORTED = "The record was not exported";
export const KEEP_AS_IS = "Change nothing";
export const KEEP_CONNECTED = "Keep it connected";
export const REVIEW_EDIT = "Review the change";
export const REVIEW_KEY = "Review the key";
export const KEY_SUPPLIED = "Supplied, and never shown again";

/** Every name a setting's input answers to: its own, and its place in the body. */
function settingNames(name: string): readonly string[] {
  return [name, `settings.${name}`];
}

/** The acts' drawers, which one is open, and for which source. */
export type OpenAct =
  | { readonly act: "connect"; readonly source: string | null }
  | { readonly act: "lark" }
  | { readonly act: "edit"; readonly source: string }
  | { readonly act: "key"; readonly source: string }
  | { readonly act: "disconnect"; readonly source: string; readonly label: string };

// ------------------------------------------------------------------------------ connect

export function ConnectDrawer({
  page,
  source,
  onClose,
  onDone,
}: {
  readonly page: ConnectorsBody;
  /** The source to open on, or null to open on the first this reader may connect. */
  readonly source: string | null;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const sources = offered(page.connectable);
  const [chosen, setChosen] = useState(source ?? sources[0]?.name ?? "");
  const picked = sources.find((one) => one.name === chosen);
  const selectId = useId();
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      title={CONNECT_TITLE}
      description={CONNECT_DESCRIPTION}
    >
      <div className="flex min-w-0 flex-col gap-3">
        {page.vault_told === "" ? null : <Note kind="not-yet">{page.vault_told}</Note>}
        {sources.length === 0 ? (
          <Note>{NOTHING_TO_CONNECT}</Note>
        ) : (
          <>
            <div className="flex flex-col gap-2">
              <Label htmlFor={selectId}>{WHICH_SOURCE}</Label>
              <select
                id={selectId}
                className="h-9 rounded-md border border-input bg-transparent px-2.5 text-sm text-ink"
                value={chosen}
                onChange={(event) => {
                  setChosen(event.target.value);
                }}
              >
                {sources.map((one) => (
                  <option key={one.name} value={one.name}>
                    {one.label}
                  </option>
                ))}
              </select>
            </div>
            {picked === undefined ? null : (
              <ConnectSource
                key={picked.name}
                source={picked}
                confirmation={page.confirm_connect}
                keyMaxChars={page.key_max_chars}
                keyBlank={page.key_blank}
                onConnected={onDone}
              />
            )}
          </>
        )}
      </div>
    </Drawer>
  );
}

export function LarkDrawer({ onClose }: { readonly onClose: () => void }) {
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      title={ACT_LABELS.connectLark}
      description={LARK_DESCRIPTION}
    >
      <ConnectLark />
    </Drawer>
  );
}

// --------------------------------------------------------------------------------- edit

/** The settings as the form starts: what the connection was made with, by setting name. */
function startingSettings(form: Connectable, current: readonly SettingValue[]): Record<string, string> {
  return Object.fromEntries(form.settings.map((one) => [one.name, current.find((was) => was.name === one.name)?.value ?? ""]));
}

export function EditDrawer({
  name,
  form,
  current,
  confirmation,
  onClose,
  onDone,
}: {
  readonly name: string;
  /** The source's form, as `GET /connectors` serves it. */
  readonly form: Connectable;
  readonly current: readonly SettingValue[];
  /** The API's sentence for what an edit agrees to. */
  readonly confirmation: string;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const [settings, setSettings] = useState<Record<string, string>>(() => startingSettings(form, current));
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];
  const prefix = `edit-${name}`;

  function ask(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setFailure(null);
    const found = form.settings
      .filter((one) => (settings[one.name] ?? "").trim() === "")
      .map((one) => ({ field: one.name, code: "blank", message: one.blank }));
    setBlank(found);
    if (found.length === 0) {
      setPending(true);
    }
  }

  function send(): void {
    setBusy(true);
    void (async () => {
      const body = { settings: Object.fromEntries(form.settings.map((one) => [one.name, settings[one.name] ?? ""])) };
      const result = await request<unknown>(editApiPath(name), { method: "POST", body });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onDone(readTold(result.data));
    })();
  }

  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open && !busy) {
          onClose();
        }
      }}
      title={`${EDIT_TITLE}: ${form.label}`}
      description={EDIT_DESCRIPTION}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {KEEP_AS_IS}
          </Button>
          <Button type="submit" form={prefix} disabled={busy}>
            {REVIEW_EDIT}
          </Button>
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        {failure === null ? null : (
          <FailureNotice failure={failure} title={NOT_EDITED} fields={form.settings.flatMap((one) => settingNames(one.name))} />
        )}
        <FieldProblems problems={problems} form={prefix} names="connector" />
        <form id={prefix} className="flex flex-col gap-4" noValidate autoComplete="off" onSubmit={ask}>
          {form.settings.map((one) => (
            <div key={one.name} className="flex flex-col gap-2">
              <Label htmlFor={`${prefix}-${one.name}`}>{one.label}</Label>
              <Input
                id={`${prefix}-${one.name}`}
                name={`settings.${one.name}`}
                value={settings[one.name] ?? ""}
                maxLength={one.max_chars}
                autoComplete="off"
                spellCheck={false}
                disabled={busy}
                {...problemAttributes(problems, prefix, settingNames(one.name))}
                onChange={(event) => {
                  setSettings({ ...settings, [one.name]: event.target.value });
                }}
              />
              <p className="m-0 text-[12.5px] leading-snug text-dim">{one.hint}</p>
              <FieldProblems problems={problems} form={prefix} names={settingNames(one.name)} />
            </div>
          ))}
        </form>
      </div>
      <ConfirmDialog
        open={pending}
        question={`Connect ${form.label} again with these settings?`}
        consequence={confirmation}
        details={
          <FactList>
            {form.settings.map((one) => (
              <Fact key={one.name} label={one.label}>
                {settings[one.name] ?? ""}
              </Fact>
            ))}
          </FactList>
        }
        confirmLabel={EDIT_TITLE}
        cancelLabel={KEEP_AS_IS}
        busy={busy}
        onConfirm={() => {
          send();
        }}
        onCancel={() => {
          setPending(false);
        }}
      />
    </Drawer>
  );
}

// ---------------------------------------------------------------------------------- key

export function KeyDrawer({
  name,
  form,
  keyBlank,
  confirmation,
  keyHeld,
  onClose,
  onDone,
}: {
  readonly name: string;
  readonly form: Connectable;
  /** The API's sentence for a blank key, said before the confirmation opens. */
  readonly keyBlank: string;
  /** The API's sentence for what replacing a key agrees to. */
  readonly confirmation: string;
  /** Whether the vault reports a key held now. Never what it is. */
  readonly keyHeld: boolean;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const secret = useSecret();
  const [present, setPresent] = useState(false);
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];
  const prefix = `key-${name}`;
  const described = problemAttributes(problems, prefix, "credential")["aria-describedby"];

  function ask(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setFailure(null);
    const found = present ? [] : [{ field: "credential", code: "blank", message: keyBlank }];
    setBlank(found);
    if (found.length === 0) {
      setPending(true);
    }
  }

  function send(): void {
    // The key leaves the field in the same call that empties it, and goes into this body only.
    const body = { credential: secret.take() };
    setPresent(false);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(keyApiPath(name), { method: "POST", body });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onDone(readTold(result.data));
    })();
  }

  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open && !busy) {
          onClose();
        }
      }}
      title={`${KEY_TITLE}: ${form.label}`}
      description={KEY_DESCRIPTION}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {KEEP_AS_IS}
          </Button>
          <Button type="submit" form={prefix} disabled={busy}>
            {REVIEW_KEY}
          </Button>
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        {failure === null ? null : <FailureNotice failure={failure} title={NOT_REPLACED} fields={["credential"]} />}
        <form id={prefix} className="flex flex-col gap-2" noValidate autoComplete="off" onSubmit={ask}>
          <SecretField
            secret={secret}
            label={form.credential_label}
            stored={keyHeld}
            description={form.credential_hint}
            disabled={busy}
            invalid={problems.some((one) => one.field === "credential")}
            onPresenceChange={setPresent}
            {...(described === undefined ? {} : { describedBy: described })}
          />
          <FieldProblems problems={problems} form={prefix} names="credential" />
        </form>
      </div>
      <ConfirmDialog
        open={pending}
        question={`Replace the key for ${form.label}?`}
        consequence={confirmation}
        details={
          <FactList>
            <Fact label={form.credential_label}>{KEY_SUPPLIED}</Fact>
          </FactList>
        }
        confirmLabel={KEY_TITLE}
        cancelLabel={KEEP_AS_IS}
        busy={busy}
        onConfirm={() => {
          send();
        }}
        onCancel={() => {
          setPending(false);
        }}
      />
    </Drawer>
  );
}

// --------------------------------------------------------------------------- disconnect

export function DisconnectDialog({
  name,
  label,
  consequence,
  onClose,
  onDone,
}: {
  readonly name: string;
  readonly label: string;
  /** The API's sentence for what disconnecting does, which says the key stays in the vault. */
  readonly consequence: string;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  function send(): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(disconnectApiPath(name), { method: "POST" });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onDone(readTold(result.data));
    })();
  }

  return (
    <ConfirmDialog
      open
      question={`${ACT_LABELS.disconnect} ${label}?`}
      consequence={consequence}
      details={failure === null ? undefined : <FailureNotice failure={failure} title={NOT_DISCONNECTED} />}
      confirmLabel={ACT_LABELS.disconnect}
      cancelLabel={KEEP_CONNECTED}
      busy={busy}
      onConfirm={() => {
        send();
      }}
      onCancel={onClose}
    />
  );
}

// ------------------------------------------------------------------------------- export

/**
 * Save one source's record as a JSON file. A read: it changes nothing, and the document it saves
 * carries no key because the API sends none. Returns the failure, or null once it is saved.
 */
export async function exportRecord(name: string, into: Document = globalThis.document): Promise<ApiFailure | null> {
  const result = await request<unknown>(exportApiPath(name));
  if (!result.ok) {
    return result.failure;
  }
  if (typeof URL.createObjectURL === "function") {
    const address = URL.createObjectURL(new Blob([JSON.stringify(result.data, null, 2)], { type: "application/json" }));
    const link = into.createElement("a");
    link.href = address;
    link.download = exportFileName(name);
    into.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(address);
  }
  return null;
}
