/**
 * Connect Lark, one screen at a time: choose what the app is for, create it, paste its App ID and
 * App Secret, add its permissions in one paste, release a version, share what it reads, then test
 * and save. Built on the kit's `ConnectFlow`, which every connector's flow shares.
 *
 * **The steps, their pictures, their links and the scopes are the API's** (`brain.ops.
 * lark_connect.steps_for`). Choosing a use or typing the App ID reads the guide again, so the
 * permissions copied are exactly the ones the test checks, and once the App ID is known every step
 * on one of the app's pages opens that page in Lark.
 *
 * **The permissions are pasted once.** "Copy all permissions" puts them on the clipboard in the
 * shape Lark's batch import reads (`scope_import`); the one-by-one list stays under it for a Lark
 * that offers no import.
 *
 * **A test says which step to redo, with its picture.** Each use's result names the steps to go
 * back to (`redo`); they are drawn with their pictures and a button to each, and marked in the step
 * list. A missing permission always sends somebody to the release step as well, because Lark cannot
 * tell a permission never added from one added and not yet released.
 *
 * **Closing keeps the place and never a secret.** The step, the uses, the platform, the App ID and
 * the Base's link are kept in the tab's memory (`kit/flowMemory.ts`) so somebody can go to Lark and
 * come back; the App Secret and the chat channel's keys are in their own fields and go when the
 * dialog does. A test and the chat channel's early save send them and leave them in their fields;
 * the final save takes them out in the call that sends them. See `pages/larkConnectQuery.ts`'
 * `THE_SECRET_STAYS_IN_ITS_FIELD`.
 *
 * **Every write is confirmed.** Saving switches uses on and can make Lark the install's staff
 * source, so both saves open the kit's `ConfirmDialog` in the API's words first.
 *
 * Task ids: M11.9.4, M10.2.1, M27.11.9
 */

import { Copy } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  ConfirmDialog,
  ConnectFlow,
  Fact,
  FactList,
  FailureState,
  FlowDialog,
  forgetFlow,
  indexOf,
  LoadingState,
  Note,
  recallFlow,
  rememberFlow,
  stepOf,
  StepSketch,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { SecretField, useSecret, type SecretHandle } from "../../components/ui/secret-field";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  guidePath,
  LARK_API_PATH,
  LARK_FLOW,
  LARK_TEST_API_PATH,
  larkBody,
  skippedPages,
  startingUses,
  stepsFor,
  toggled,
  verdictWords,
  type LarkEvents,
  type LarkGuide,
  type LarkSaved,
  type LarkStep,
  type LarkTested,
} from "../larkConnectQuery";
import { WikiSpaces } from "./WikiSpaces";

export const CONNECT_LARK = "Connect Lark";
export const ADD_A_USE = "Add a use to Lark";
export const FLOW_DESCRIPTION =
  "One screen at a time. Close it whenever you need to: it keeps your place, but not the App Secret.";
export const WHAT_FOR = "What the Lark app is for";
export const PLATFORM = "Lark platform";
export const APP_ID_HINT = "Starts with cli_, exactly as Lark shows it. It is not a secret.";
export const SECRET_HINT = "Kept in the vault when you save, and never shown again.";
export const PASTE_AGAIN =
  "Testing sends the App ID and App Secret to Lark as you type them, because this system never reads a kept secret back. Paste the App Secret here.";
export const COPY_ALL = "Copy all permissions";
export const COPIED = "Copied. In Lark, click Batch import (or Import scopes) and paste.";
export const NOT_COPIED = "Your browser did not allow copying. Select the text below, copy it, and paste it into Lark.";
export const ONE_AT_A_TIME = "Or add them one at a time";
export const EVENTS_ADDRESS = "Events address to paste in Lark";
export const COPY_ADDRESS = "Copy the address";
export const NO_ADDRESS =
  "This install names no address of its own yet, so there is no events address to paste. Set the install's sign-in redirect address first.";
export const LARK_EVENTS = "Lark's events";
export const SAVE_CHANNEL = "Save the chat channel now";
export const CHANNEL_SAVED = "The chat channel is saved. Now point Lark's events at this install.";
export const BASE_LINK = "Link of the Base to read";
export const BASE_LINK_HINT = "Copied from the browser while the Base is open. It contains /base/ and the Base's token.";
export const TEST_CONNECTION = "Test connection";
export const SAVE_LARK = "Save and switch on";
export const KEEP_AS_IS = "Change nothing";
export const NOT_SAVED = "Lark was not connected";
export const NOT_TESTED = "The test did not run";
export const SECRET_SUPPLIED = "Supplied, and never shown again";
export const TESTING = "Asking Lark.";
export const TEST_RESULTS = "Test results";
export const LOADING_GUIDE = "Reading how Lark is connected.";
export const OPEN_CAPABILITIES = "Open Capabilities";
export const OPEN_PEOPLE = "Open People";

/** Where a Base's tables are listed by title, and where a person is granted them. */
export const CAPABILITIES_SCREEN = "/capabilities";
export const PEOPLE_SCREEN = "/people";

export function goTo(position: number): string {
  return `Go to step ${position}`;
}

const FORM = "connect-lark";
const FIELDS = ["app_id", "app_secret", "uses", "platform", "base_link", "encrypt_key", "verification_token"];

/** Where the flow was left: plain values only, never a secret. See `kit/flowMemory.ts`. */
export interface LarkPlace {
  readonly at: string;
  readonly uses: readonly string[] | null;
  readonly platform: string;
  readonly appId: string;
  readonly baseLink: string | null;
}

/** Where to open the flow: a step, and any uses to add to what is on. */
export interface LarkStart {
  readonly at?: string | undefined;
  readonly add?: readonly string[] | undefined;
}

function when(at: string | null | undefined): string {
  return at === null || at === undefined ? "never" : new Date(at).toLocaleString();
}

/** A secret field's problem, in the two props the kit's field takes for it. */
function secretProblems(problems: Parameters<typeof problemAttributes>[0], field: string): { invalid: boolean; describedBy?: string } {
  const attributes = problemAttributes(problems, FORM, field);
  const describedBy = attributes["aria-describedby"];
  return describedBy === undefined ? { invalid: attributes["aria-invalid"] === true } : { invalid: attributes["aria-invalid"] === true, describedBy };
}

/** Where Lark's events go and whether they are arriving: the API's sentence and three instants. */
function EventsPanel({ events }: { readonly events: LarkEvents }) {
  return (
    <section aria-label={LARK_EVENTS} className="flex min-w-0 flex-col gap-2 rounded-md border border-line p-3">
      <h4 className="m-0 text-[13px] font-semibold text-ink">{LARK_EVENTS}</h4>
      <p role="status" className="m-0 text-[12.5px] text-body">
        {events.told}
      </p>
      <FactList>
        <Fact label="Last message received">{when(events.last_received)}</Fact>
        <Fact label="Last request refused">
          {when(events.last_refused)}
          {events.refused_because ? ` (${events.refused_because.replaceAll("_", " ")})` : null}
        </Fact>
        <Fact label="Last reply">
          {when(events.last_reply)}
          {events.reply_outcome ? ` (${events.reply_outcome})` : null}
        </Fact>
      </FactList>
    </section>
  );
}

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

/** The steps a result sends somebody back to, each with its picture and a way there. */
function RedoSteps({
  steps,
  all,
  onGo,
}: {
  readonly steps: readonly LarkStep[];
  readonly all: readonly LarkStep[];
  readonly onGo: (key: string) => void;
}) {
  if (steps.length === 0) {
    return null;
  }
  return (
    <ul aria-label="Steps to go back to" className="m-0 flex list-none flex-col gap-2 p-0">
      {steps.map((step) => {
        const position = indexOf(all, step.key) + 1;
        return (
          <li key={step.key} className="flex min-w-0 items-center gap-3 rounded-md border border-warn bg-warn-wash p-2">
            <StepSketch sketch={step.sketch} className="w-28 shrink-0 rounded sm:w-36" />
            <div className="flex min-w-0 flex-col gap-1.5">
              <p className="m-0 text-[12.5px] font-medium text-ink">
                {stepOf(position - 1, all.length)}: {step.title}
              </p>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="min-h-11 self-start sm:min-h-8"
                onClick={() => {
                  onGo(step.key);
                }}
              >
                {goTo(position)}
              </Button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Results({ guide, tested, onGo }: { readonly guide: LarkGuide; readonly tested: LarkTested; readonly onGo: (key: string) => void }) {
  return (
    <section aria-label={TEST_RESULTS} className="flex min-w-0 flex-col gap-3">
      <Note kind={tested.accepted ? "done" : "not-yet"}>{tested.told}</Note>
      <RedoSteps steps={stepsFor(guide, tested.redo)} all={guide.steps} onGo={onGo} />
      {tested.uses.length === 0 ? null : (
        <ul aria-label="What the test found for each use" className="m-0 flex list-none flex-col gap-3 p-0">
          {tested.uses.map((one) => (
            <li key={one.name} className="flex min-w-0 flex-col gap-1.5 border-b border-line pb-3 last:border-b-0">
              <p className="m-0 text-[13px] text-ink">
                <span className="font-semibold">{one.label}</span>
                {": "}
                <span className={one.verdict === "working" ? "text-ok" : "text-warn"}>{verdictWords(one.verdict)}</span>
              </p>
              <p className="m-0 text-[12.5px] text-dim">{one.told}</p>
              {one.missing.length === 0 ? null : (
                <ul aria-label={`Permissions to add for ${one.label}`} className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                  {one.missing.map((scope) => (
                    <li key={scope}>
                      <code className="rounded bg-sunk px-1.5 py-0.5 text-[12px]">{scope}</code>
                    </li>
                  ))}
                </ul>
              )}
              <RedoSteps steps={stepsFor(guide, one.redo)} all={guide.steps} onGo={onGo} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The labelled plain field for the Base's link. */
function PlainField({
  name,
  label,
  hint,
  value,
  problems,
  disabled,
  onChange,
}: {
  readonly name: string;
  readonly label: string;
  readonly hint: string;
  readonly value: string;
  readonly problems: Parameters<typeof problemAttributes>[0];
  readonly disabled: boolean;
  readonly onChange: (value: string) => void;
}) {
  const id = `${FORM}-${name}`;
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        name={name}
        value={value}
        autoComplete="off"
        autoCapitalize="off"
        spellCheck={false}
        disabled={disabled}
        {...problemAttributes(problems, FORM, name, `${id}-hint`)}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <p id={`${id}-hint`} className="m-0 text-[12.5px] leading-snug text-dim">
        {hint}
      </p>
      <FieldProblems problems={problems} form={FORM} names={name} />
    </div>
  );
}

function Flow({
  guide,
  place,
  onPlace,
  onAppId,
  onRead,
  onDone,
}: {
  readonly guide: LarkGuide;
  readonly place: LarkPlace;
  readonly onPlace: (next: Partial<LarkPlace>) => void;
  /** Ask the guide again with the App ID typed, so the steps link to the app's own pages. */
  readonly onAppId: () => void;
  /** Read the guide again, after something this flow saved changed where Lark stands. */
  readonly onRead: () => void;
  readonly onDone: (told: string) => void;
}) {
  const secret = useSecret();
  const encryptKey = useSecret();
  const verificationToken = useSecret();
  const [secretTyped, setSecretTyped] = useState(false);
  const [encryptTyped, setEncryptTyped] = useState(false);
  const [verifyTyped, setVerifyTyped] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<"save" | "channel" | null>(null);
  const [tested, setTested] = useState<LarkTested | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [copy, setCopy] = useState<"idle" | "done" | "failed">("idle");
  const [channelSaved, setChannelSaved] = useState(false);
  const platformId = useId();

  const steps = guide.steps;
  const chosen = guide.chosen;
  const at = indexOf(steps, place.at);
  const current = steps[at]?.key ?? "";
  const chat = chosen.includes("chat_channel");
  const base = chosen.includes("knowledge_base");
  const baseLink = place.baseLink ?? guide.base;
  const mayAll = chosen.length > 0 && guide.uses.filter((one) => chosen.includes(one.name)).every((one) => one.may_switch_on);
  const problems = failure?.problems ?? [];
  const typed = place.appId.trim() !== "" && secretTyped;
  const held = guide.uses.some((one) => one.switched_on);
  const flagged = new Set(tested === null ? [] : [...tested.redo, ...tested.uses.flatMap((one) => one.redo)]);

  const go = useCallback(
    (key: string) => {
      onPlace({ at: key });
    },
    [onPlace],
  );

  function body(uses: readonly string[], finalSave: boolean) {
    // The last save takes every secret out of its field in the call that sends it; a test and the
    // chat channel's early save leave them there for the save that follows.
    const read = (handle: SecretHandle): string => (finalSave ? handle.take() : handle.peek());
    return larkBody(place.appId, read(secret), uses, guide.platform, baseLink, {
      encryptKey: read(encryptKey),
      verificationToken: read(verificationToken),
    });
  }

  function test(): void {
    setBusy(true);
    setFailure(null);
    setTested(null);
    void (async () => {
      const result = await request<LarkTested>(LARK_TEST_API_PATH, { method: "POST", body: body(chosen, false) });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setTested(result.data);
    })();
  }

  function save(which: "save" | "channel"): void {
    const sent = which === "save" ? body(chosen, true) : body(["chat_channel"], false);
    setBusy(true);
    void (async () => {
      const result = await request<LarkSaved>(LARK_API_PATH, { method: "POST", body: sent });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      if (which === "channel") {
        setChannelSaved(true);
        onRead();
        return;
      }
      onDone(result.data.told);
    })();
  }

  const showCredentials = current === "credentials" || (current === "test" && !typed);
  const showChatKeys = current === "events_keys" || (current === "test" && chat && !(encryptTyped && verifyTyped));
  const showBase = current === "share_base" || (current === "test" && base && baseLink.trim() === "");

  const shared = (
    <>
      <div hidden={!showCredentials} className="flex min-w-0 flex-col gap-3">
        {current === "test" ? <Note>{PASTE_AGAIN}</Note> : null}
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor={`${FORM}-app_id`}>App ID</Label>
          <Input
            id={`${FORM}-app_id`}
            name="app_id"
            value={place.appId}
            placeholder="cli_"
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            disabled={busy}
            {...problemAttributes(problems, FORM, "app_id", `${FORM}-app_id-hint`)}
            onChange={(event) => {
              onPlace({ appId: event.target.value });
            }}
            onBlur={onAppId}
          />
          <p id={`${FORM}-app_id-hint`} className="m-0 text-[12.5px] leading-snug text-dim">
            {APP_ID_HINT}
          </p>
          <FieldProblems problems={problems} form={FORM} names="app_id" />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <SecretField
            id={`${FORM}-app_secret`}
            secret={secret}
            label="App Secret"
            stored={held}
            description={SECRET_HINT}
            disabled={busy}
            {...secretProblems(problems, "app_secret")}
            onPresenceChange={setSecretTyped}
          />
          <FieldProblems problems={problems} form={FORM} names="app_secret" />
        </div>
      </div>
      <div hidden={!showChatKeys} className="flex min-w-0 flex-col gap-3">
        <SecretField
          id={`${FORM}-encrypt_key`}
          secret={encryptKey}
          label="Encrypt Key"
          stored={held}
          description="From Events & Callbacks, Encryption Strategy. Kept in the vault and never shown again."
          disabled={busy}
          {...secretProblems(problems, "encrypt_key")}
          onPresenceChange={setEncryptTyped}
        />
        <FieldProblems problems={problems} form={FORM} names="encrypt_key" />
        <SecretField
          id={`${FORM}-verification_token`}
          secret={verificationToken}
          label="Verification Token"
          stored={held}
          description="From the same tab. Kept in the vault with the Encrypt Key and never shown again."
          disabled={busy}
          {...secretProblems(problems, "verification_token")}
          onPresenceChange={setVerifyTyped}
        />
        <FieldProblems problems={problems} form={FORM} names="verification_token" />
      </div>
      <div hidden={!showBase} className="min-w-0">
        <PlainField
          name="base_link"
          label={BASE_LINK}
          hint={BASE_LINK_HINT}
          value={baseLink}
          problems={problems}
          disabled={busy}
          onChange={(value) => {
            onPlace({ baseLink: value });
          }}
        />
      </div>
    </>
  );

  const failureNotice =
    failure === null ? null : <FailureNotice failure={failure} title={tested === null && pending === null ? NOT_TESTED : NOT_SAVED} fields={FIELDS} />;

  const panels: Record<string, ReactNode> = {
    choose: (
      <fieldset className="m-0 flex min-w-0 flex-col gap-2.5 border-0 p-0">
        <legend className="mb-1 text-[13px] font-semibold text-ink">{WHAT_FOR}</legend>
        {guide.uses.map((one) => (
          <label key={one.name} className="flex min-w-0 items-start gap-2.5 rounded-md border border-line p-3 text-[13px]">
            <input
              type="checkbox"
              name="uses"
              value={one.name}
              className="mt-0.5 size-4 shrink-0"
              checked={chosen.includes(one.name)}
              disabled={busy || !one.may_switch_on}
              onChange={(event) => {
                setTested(null);
                onPlace({ uses: toggled(guide.uses, chosen, one.name, event.target.checked) });
              }}
            />
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="font-medium text-ink">{one.label}</span>
              <span className="text-[12.5px] leading-snug text-dim">{one.what}</span>
              {one.switched_on ? <span className="text-[12px] font-medium text-ok">Switched on</span> : null}
            </span>
          </label>
        ))}
        <FieldProblems problems={problems} form={FORM} names="uses" />
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor={platformId}>{PLATFORM}</Label>
          <select
            id={platformId}
            className="h-11 rounded-md border border-input bg-transparent px-2.5 text-sm text-ink sm:h-9"
            value={guide.platform}
            disabled={busy}
            onChange={(event) => {
              onPlace({ platform: event.target.value });
            }}
          >
            {guide.platforms.map((one) => (
              <option key={one} value={one}>
                {one}
              </option>
            ))}
          </select>
        </div>
      </fieldset>
    ),
    permissions: (
      <div className="flex min-w-0 flex-col gap-3">
        <Button
          type="button"
          className="min-h-11 self-start sm:min-h-9"
          disabled={guide.scopes.length === 0}
          onClick={() => {
            void (async () => {
              setCopy((await copied(guide.scope_import)) ? "done" : "failed");
            })();
          }}
        >
          <Copy aria-hidden />
          {COPY_ALL}
        </Button>
        {copy === "done" ? <Note kind="done">{COPIED}</Note> : null}
        {copy === "failed" ? (
          <>
            <Note kind="not-yet">{NOT_COPIED}</Note>
            <textarea
              readOnly
              aria-label="The permissions to paste into Lark"
              className="min-h-32 w-full rounded-md border border-input bg-ground p-2 font-mono text-[12px] text-ink"
              value={guide.scope_import}
            />
          </>
        ) : null}
        <details className="rounded-md border border-line p-3 text-[13px]">
          <summary className="cursor-pointer font-medium text-ink">{ONE_AT_A_TIME}</summary>
          <ul aria-label="Permissions to add" className="m-0 mt-2 flex list-none flex-col gap-2 p-0">
            {guide.scopes.map((one) => (
              <li key={one.name} className="flex min-w-0 flex-col gap-0.5">
                <code className="self-start rounded bg-sunk px-1.5 py-0.5 text-[12px] [overflow-wrap:anywhere]">{one.name}</code>
                <span className="text-[12.5px] text-dim">
                  {one.read_only ? "Only reads" : "The one write"}: {one.what}
                </span>
              </li>
            ))}
          </ul>
        </details>
      </div>
    ),
    events_keys: (
      <div className="flex min-w-0 flex-col gap-3">
        {current === "events_keys" ? failureNotice : null}
        <Button
          type="button"
          variant="outline"
          className="min-h-11 self-start sm:min-h-9"
          disabled={busy || !typed || !encryptTyped || !verifyTyped || !mayAll}
          onClick={() => {
            setPending("channel");
          }}
        >
          {SAVE_CHANNEL}
        </Button>
        {!typed ? <Note>Paste the App ID and App Secret on step 3 first.</Note> : null}
        {channelSaved ? <Note kind="done">{CHANNEL_SAVED}</Note> : null}
      </div>
    ),
    events_address: (
      <div className="flex min-w-0 flex-col gap-3">
        {guide.events_address === "" ? (
          <Note kind="not-yet">{NO_ADDRESS}</Note>
        ) : (
          <div className="flex min-w-0 flex-col gap-1.5">
            <p className="m-0 text-[12.5px] text-dim">{EVENTS_ADDRESS}</p>
            <code className="rounded bg-sunk px-2 py-1.5 text-[12px] [overflow-wrap:anywhere]">{guide.events_address}</code>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11 self-start sm:min-h-8"
              onClick={() => {
                void copied(guide.events_address);
              }}
            >
              <Copy aria-hidden />
              {COPY_ADDRESS}
            </Button>
          </div>
        )}
        {guide.events === null || guide.events === undefined ? null : <EventsPanel events={guide.events} />}
      </div>
    ),
    wiki_spaces: (
      <WikiSpaces
        tested={tested}
        may={guide.uses.some((one) => one.name === "knowledge_wiki" && one.may_switch_on)}
        skipped={skippedPages(guide)}
      />
    ),
    base_access: (
      <div className="flex min-w-0 flex-wrap gap-2">
        <Link to={CAPABILITIES_SCREEN} className="text-[13px] text-acc-text underline underline-offset-4">
          {OPEN_CAPABILITIES}
        </Link>
        <Link to={PEOPLE_SCREEN} className="text-[13px] text-acc-text underline underline-offset-4">
          {OPEN_PEOPLE}
        </Link>
      </div>
    ),
    test: (
      <div className="flex min-w-0 flex-col gap-3">
        {guide.vault_told === "" ? null : <Note kind="not-yet">{guide.vault_told}</Note>}
        {current === "test" ? failureNotice : null}
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" className="min-h-11 sm:min-h-9" disabled={busy || !mayAll || !typed} onClick={test}>
            {TEST_CONNECTION}
          </Button>
          <Button
            type="button"
            className="min-h-11 sm:min-h-9"
            disabled={busy || !mayAll || !typed || (tested !== null && !tested.accepted)}
            onClick={() => {
              setPending("save");
            }}
          >
            {SAVE_LARK}
          </Button>
        </div>
        {busy ? (
          <p role="status" className="m-0 text-[12.5px] text-dim">
            {TESTING}
          </p>
        ) : null}
        <p className="m-0 text-[12px] text-dim">{guide.test_note}</p>
        {tested === null ? null : <Results guide={guide} tested={tested} onGo={go} />}
      </div>
    ),
  };

  const saving = pending === "save" ? chosen : ["chat_channel"];
  return (
    <>
      <ConnectFlow
        steps={steps}
        at={at}
        onAt={(index) => {
          const next = steps[index];
          if (next !== undefined) {
            go(next.key);
          }
        }}
        panels={panels}
        shared={shared}
        flagged={flagged}
        onNext={(key) => {
          if (key === "credentials") {
            onAppId();
          }
        }}
      />
      <ConfirmDialog
        open={pending !== null}
        question={pending === "channel" ? `${SAVE_CHANNEL}?` : `${SAVE_LARK}?`}
        consequence={
          "The App Secret is kept in the vault for each use below and the uses are switched on. " +
          (saving.includes("staff_list") ? "Switching the staff list on makes Lark this install's staff source. " : "") +
          guide.knowledge_note
        }
        details={
          <FactList>
            {guide.uses
              .filter((one) => saving.includes(one.name))
              .map((one) => (
                <Fact key={one.name} label={one.label}>
                  Switched on
                </Fact>
              ))}
            <Fact label="App Secret">{SECRET_SUPPLIED}</Fact>
            {saving.includes("chat_channel") ? <Fact label="Encrypt Key and Verification Token">{SECRET_SUPPLIED}</Fact> : null}
          </FactList>
        }
        confirmLabel={pending === "channel" ? SAVE_CHANNEL : SAVE_LARK}
        cancelLabel={KEEP_AS_IS}
        busy={busy}
        danger={false}
        onConfirm={() => {
          if (pending !== null) {
            save(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </>
  );
}

/** The flow in its dialog, reading the guide for the uses chosen and keeping its place. */
export function LarkFlow({
  start,
  onClose,
  onDone,
}: {
  readonly start?: LarkStart | undefined;
  readonly onClose: () => void;
  /** Told the API's sentence after the final save. The flow's place is forgotten then. */
  readonly onDone: (told: string) => void;
}) {
  const [place, setPlace] = useState<LarkPlace>(() => {
    const kept = recallFlow<LarkPlace>(LARK_FLOW);
    const from: LarkPlace = kept ?? { at: "choose", uses: null, platform: "", appId: "", baseLink: null };
    return start?.at === undefined ? from : { ...from, at: start.at };
  });
  // The App ID the guide was last asked with, which moves when the field is left, not per key.
  const [askedAppId, setAskedAppId] = useState(place.appId.trim());
  const [generation, setGeneration] = useState(0);
  const answer = useResource<LarkGuide>(guidePath(place.uses, place.platform, askedAppId), generation);
  // The last guide read stays drawn while the next one is asked for, so choosing a use does not
  // unmount the fields and lose what was typed into them.
  const [guide, setGuide] = useState<LarkGuide | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (answer.data === null) {
      return;
    }
    setGuide(answer.data);
    if (!started.current) {
      started.current = true;
      const data = answer.data;
      setPlace((was) => ({
        ...was,
        appId: was.appId === "" ? data.app_id : was.appId,
        uses: was.uses === null && (start?.add?.length ?? 0) > 0 ? startingUses(data, start?.add ?? []) : was.uses,
      }));
    }
  }, [answer.data, start]);

  useEffect(() => {
    rememberFlow<LarkPlace>(LARK_FLOW, place);
  }, [place]);

  const onPlace = useCallback((next: Partial<LarkPlace>) => {
    setPlace((was) => ({ ...was, ...next }));
  }, []);

  const connected = guide?.connected === true;
  let body: ReactNode;
  if (guide === null) {
    body = answer.failure === null ? <LoadingState label={LOADING_GUIDE} rows={4} /> : <FailureState failure={answer.failure} />;
  } else {
    body = (
      <Flow
        guide={guide}
        place={place}
        onPlace={onPlace}
        onAppId={() => {
          setAskedAppId(place.appId.trim());
        }}
        onRead={() => {
          setGeneration((one) => one + 1);
        }}
        onDone={(told) => {
          forgetFlow(LARK_FLOW);
          onDone(told);
        }}
      />
    );
  }
  return (
    <FlowDialog title={connected ? ADD_A_USE : CONNECT_LARK} description={FLOW_DESCRIPTION} onClose={onClose}>
      {body}
    </FlowDialog>
  );
}
