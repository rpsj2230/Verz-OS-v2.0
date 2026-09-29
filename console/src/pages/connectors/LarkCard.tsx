/**
 * Lark, once it is connected: which platform, which uses are switched on and how each stands, when
 * it was last tested and what each use came to, and when the staff list was last read, with Test,
 * Manage and Disconnect beside them.
 *
 * **This replaces the Connect Lark button, it does not sit beside it.** The owner found the button
 * still offered, and still opening the setup, after Lark was connected. So a page asks the API
 * whether anything is switched on (`LarkView.connected`) and draws this card when it is; adding a
 * use, replacing the App Secret and testing each reopen the flow at the step that does it.
 *
 * **Test reopens the flow at its last step and asks for the App Secret there.** The application
 * may write a key and never reads one back, so a test takes the secret as it is typed; the card
 * says when the last test ran and what it found, which needs no secret at all.
 *
 * **Switching off keeps the key.** Each use asks its own authority, the confirmation says the key
 * stays in the vault and what switching the staff list off does to the staff source, in the API's
 * words (`switch_off_note`, `staff_off_note`), and the page reads everything again afterwards.
 *
 * Task ids: M11.9.4, M27.11.9
 */

import { ChevronDown, PlugZap, Settings } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Advanced, Chip, ConfirmDialog, Fact, FactList, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { FailureNotice } from "../../ui/FailureNotice";
import {
  LARK_SWITCH_OFF_API_PATH,
  switchedOn,
  verdictWords,
  type LarkGuide,
  type LarkSwitchedOff,
  type LarkUse,
} from "../larkConnectQuery";
import { readRuns, RUNS_API_PATH } from "../staffSourcesQuery";
import { outcomeWords, when } from "../staff-sources/staffSourceWords";
import type { LarkStart } from "./LarkFlow";

export const LARK_HEADING = "Lark";
export const LARK_CONNECTED = "Connected. One Lark app, switched on for the uses below.";
export const PLATFORM_LABEL = "Platform";
export const USES_LABEL = "Switched on";
export const LAST_TEST_LABEL = "Last test";
export const LAST_SYNC_LABEL = "Last staff sync";
export const NEVER_TESTED = "Not tested from the console yet";
export const NO_SYNC_YET = "No sync yet";
export const TEST = "Test";
export const MANAGE = "Manage";
export const ADD_A_USE = "Add a use";
export const REPLACE_SECRET = "Replace the App Secret";
export const DISCONNECT = "Disconnect";
export const KEEP_ON = "Keep it on";
export const NOT_SWITCHED_OFF = "Nothing was switched off";
export const OPEN_STAFF_SOURCES = "Open Staff sources";
export const APP_ID_LABEL = "App ID";

export function switchOffLabel(label: string): string {
  return `Switch off ${label}`;
}

const PLATFORM_WORDS: Readonly<Record<string, string>> = {
  "larksuite.com": "Lark (larksuite.com)",
  "feishu.cn": "Feishu (feishu.cn)",
};

/** When the staff list was last read, for a card with the staff list on; nothing for anybody else. */
function LastSync({ on }: { readonly on: boolean }) {
  const runs = useResource<unknown>(on ? RUNS_API_PATH : null);
  if (!on || runs.failure !== null || runs.busy) {
    return null;
  }
  const last = readRuns(runs.data)[0];
  return <Fact label={LAST_SYNC_LABEL}>{last === undefined ? NO_SYNC_YET : `${when(last.finished_at)}, ${outcomeWords(last.outcome).toLocaleLowerCase("en-GB")}`}</Fact>;
}

export function LarkCard({
  guide,
  onOpen,
  onDone,
  staffSourcesLink = true,
}: {
  readonly guide: LarkGuide;
  /** Reopen the flow at a step: `choose` to add a use, `credentials` for the key, `test` to test. */
  readonly onOpen: (start: LarkStart) => void;
  /** Told the API's sentence after a switch off, so the page can say it and read again. */
  readonly onDone: (told: string) => void;
  /** Whether to link to Staff sources when the staff list is on; that page itself does not. */
  readonly staffSourcesLink?: boolean;
}) {
  const on = switchedOn(guide);
  const mayAny = on.some((one) => one.may_switch_on);
  const mayAll = on.length > 0 && on.every((one) => one.may_switch_on);
  const [off, setOff] = useState<readonly LarkUse[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const staffOn = on.some((one) => one.name === "staff_list");
  const test = guide.last_test ?? null;

  function switchOff(uses: readonly LarkUse[]): void {
    setBusy(true);
    void (async () => {
      const result = await request<LarkSwitchedOff>(LARK_SWITCH_OFF_API_PATH, {
        method: "POST",
        body: { uses: uses.map((one) => one.name) },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setOff(null);
      setFailure(null);
      onDone(result.data.told);
    })();
  }

  return (
    <SectionCard
      title={LARK_HEADING}
      lede={LARK_CONNECTED}
      action={
        mayAny ? (
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                onOpen({ at: "test" });
              }}
            >
              <PlugZap aria-hidden />
              {TEST}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" aria-label={`${MANAGE} Lark`}>
                  <Settings aria-hidden />
                  <span className="hidden sm:inline">{MANAGE}</span>
                  <ChevronDown aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuItem
                  onSelect={() => {
                    onOpen({ at: "choose" });
                  }}
                >
                  {ADD_A_USE}
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => {
                    onOpen({ at: "credentials" });
                  }}
                >
                  {REPLACE_SECRET}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {on
                  .filter((one) => one.may_switch_on)
                  .map((one) => (
                    <DropdownMenuItem
                      key={one.name}
                      onSelect={() => {
                        setFailure(null);
                        setOff([one]);
                      }}
                    >
                      {switchOffLabel(one.label)}
                    </DropdownMenuItem>
                  ))}
                {mayAll ? (
                  <DropdownMenuItem
                    className="text-crit"
                    onSelect={() => {
                      setFailure(null);
                      setOff(on);
                    }}
                  >
                    {DISCONNECT}
                  </DropdownMenuItem>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        ) : undefined
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        <FactList>
          <Fact label={PLATFORM_LABEL}>{PLATFORM_WORDS[guide.platform] ?? guide.platform}</Fact>
          <Fact label={USES_LABEL}>
            <ul aria-label={USES_LABEL} className="m-0 flex list-none flex-col gap-1.5 p-0">
              {on.map((one) => (
                <li key={one.name} className="flex min-w-0 flex-col gap-0.5">
                  <span className="font-medium">{one.label}</span>
                  <span className="text-[12.5px] text-dim">{one.status}</span>
                </li>
              ))}
            </ul>
          </Fact>
          <Fact label={LAST_TEST_LABEL}>
            {test === null ? (
              NEVER_TESTED
            ) : (
              <span className="flex min-w-0 flex-col gap-1.5">
                <span>{when(test.at)}</span>
                <span className="flex flex-wrap gap-1.5">
                  {test.accepted ? null : <Chip>Credential refused</Chip>}
                  {test.uses.map((one) => (
                    <Chip key={one.name}>
                      {one.label}: {verdictWords(one.verdict)}
                    </Chip>
                  ))}
                </span>
              </span>
            )}
          </Fact>
          <LastSync on={staffOn} />
        </FactList>
        {staffOn && staffSourcesLink ? (
          <p className="m-0 text-[12.5px]">
            <Link to={guide.staff_sources_screen} className="text-acc-text underline underline-offset-4">
              {OPEN_STAFF_SOURCES}
            </Link>{" "}
            for the staff list's runs, a dry run and the leavers.
          </p>
        ) : null}
        {guide.app_id === "" ? null : (
          <Advanced>
            <FactList>
              <Fact label={APP_ID_LABEL}>
                <Chip mono>{guide.app_id}</Chip>
              </Fact>
            </FactList>
          </Advanced>
        )}
      </div>
      <ConfirmDialog
        open={off !== null}
        question={off !== null && off.length === on.length && on.length > 1 ? `${DISCONNECT} Lark?` : `${switchOffLabel(off?.[0]?.label ?? "")}?`}
        consequence={guide.switch_off_note + (off?.some((one) => one.name === "staff_list") === true ? ` ${guide.staff_off_note}` : "")}
        details={
          <div className="flex flex-col gap-2">
            <FactList>
              {(off ?? []).map((one) => (
                <Fact key={one.name} label={one.label}>
                  Switched off
                </Fact>
              ))}
            </FactList>
            {failure === null ? null : <FailureNotice failure={failure} title={NOT_SWITCHED_OFF} />}
          </div>
        }
        confirmLabel={off !== null && off.length > 1 ? DISCONNECT : "Switch off"}
        cancelLabel={KEEP_ON}
        busy={busy}
        onConfirm={() => {
          if (off !== null) {
            switchOff(off);
          }
        }}
        onCancel={() => {
          setOff(null);
        }}
      />
      {guide.vault_told === "" ? null : <Note kind="not-yet">{guide.vault_told}</Note>}
    </SectionCard>
  );
}
