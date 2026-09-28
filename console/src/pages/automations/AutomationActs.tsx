/**
 * The five changes an automation's page makes, each sent only from a confirmation.
 *
 * **Every change carries the confirmation the page was sent.** It is a digest over the automation as
 * the page drew it: its owner, its schedule, its next run and whether it is removed. The API
 * recomputes it before writing, so a pause confirmed over an automation somebody adopted a minute
 * ago is refused with the API's sentence ("look again") and nothing is written.
 *
 * **Changing the schedule says what it accepts before anything is sent**: every day, every weekday
 * or one day a week, at a whole hour in UTC, in the API's own sentence. The three choices are lists
 * with a value always chosen, so the form cannot be sent blank, and it opens the same confirmation
 * as every other change with the new schedule in it.
 *
 * **It decides nothing.** Which changes are offered is what the API said this reader may do, and the
 * API decides again when the change arrives.
 *
 * Task ids: M27.12.3, M27.15.37, M39.6.1.5
 */

import { useId, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, Drawer } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { readNotChanged } from "../agentAutomationsQuery";
import { ACT_LABELS } from "./automationActions";
import { changeApiPath, dateWords, readAutomationDetail, type AutomationDetail, type ChangeAct, type CadenceFields } from "./automationsQuery";

export const NOT_CHANGED = "Nothing was changed";
export const KEEP_IT = "Keep it as it is";
export const SCHEDULE_TITLE = "Change the schedule";
export const EVERY_LABEL = "How often";
export const DAY_LABEL = "Day";
export const HOUR_LABEL = "Hour (UTC)";
export const REVIEW_SCHEDULE = "Review the change";
export const NEXT_RUN_AFTER_RESUME = "Its next run";

/** The three cadences, as the API spells them, and how each reads. */
export const EVERY_WORDS: Readonly<Record<string, string>> = Object.freeze({
  day: "Every day",
  weekday: "Every weekday",
  week: "One day a week",
});

/** What each change says when it is done. */
export const DONE_WORDS: Readonly<Record<ChangeAct, string>> = Object.freeze({
  pause: "Paused.",
  resume: "Resumed.",
  reschedule: "Schedule changed.",
  remove: "Removed.",
  adopt: "Adopted. It runs as you once somebody else resumes it.",
});

/** A cadence in the words the confirmation shows. */
export function cadenceWords(cadence: CadenceFields, weekdays: readonly string[]): string {
  const hour = `${String(cadence.hourUtc).padStart(2, "0")}:00 UTC`;
  if (cadence.every === "week" && cadence.weekday !== undefined) {
    return `Every ${weekdays[cadence.weekday] ?? "week"} at ${hour}`;
  }
  return `${EVERY_WORDS[cadence.every] ?? cadence.every} at ${hour}`;
}

/** One change, confirmed: what it will do, to what, and the API's answer. */
export function ChangeDialog({
  detail,
  act,
  cadence,
  onClose,
  onDone,
}: {
  readonly detail: AutomationDetail;
  readonly act: ChangeAct;
  /** The new schedule, for a schedule change only. */
  readonly cadence?: CadenceFields | undefined;
  readonly onClose: () => void;
  readonly onDone: (told: string, fresh: AutomationDetail | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ readonly failure: ApiFailure; readonly sentence?: string } | null>(null);

  function send(): void {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const body: Record<string, unknown> = { confirmation: detail.confirmation };
      if (cadence !== undefined) {
        body["every"] = cadence.every;
        body["hour_utc"] = cadence.hourUtc;
        if (cadence.weekday !== undefined) {
          body["weekday"] = cadence.weekday;
        }
      }
      const result = await request<unknown>(changeApiPath(detail.row.id, act), { method: "POST", body });
      setBusy(false);
      if (!result.ok) {
        const refused = result.failure.status === 409 ? readNotChanged(result.body) : null;
        setFailure(refused === null ? { failure: result.failure } : { failure: result.failure, sentence: refused.sentence });
        return;
      }
      onDone(DONE_WORDS[act], readAutomationDetail(result.data));
    })();
  }

  const details =
    act === "reschedule" && cadence !== undefined
      ? `New schedule: ${cadenceWords(cadence, detail.weekdays)}.`
      : act === "resume" && detail.resumeBecomes !== undefined
        ? `${NEXT_RUN_AFTER_RESUME}: ${dateWords(detail.resumeBecomes) ?? ""}.`
        : undefined;

  return (
    <ConfirmDialog
      open
      question={`${ACT_LABELS[act]} ${detail.row.name}?`}
      consequence={detail.confirm[act]}
      details={
        details === undefined && failure === null ? undefined : (
          <div className="flex flex-col gap-2">
            {details === undefined ? null : <p className="m-0">{details}</p>}
            {failure === null ? null : (
              <FailureNotice
                failure={failure.failure}
                title={NOT_CHANGED}
                {...(failure.sentence === undefined ? {} : { sentence: failure.sentence })}
              />
            )}
          </div>
        )
      }
      confirmLabel={ACT_LABELS[act]}
      cancelLabel={KEEP_IT}
      busy={busy}
      onConfirm={() => {
        send();
      }}
      onCancel={onClose}
    />
  );
}

const SELECT =
  "min-h-11 w-full rounded-md border border-line bg-panel px-2 text-[13px] text-ink outline-hidden focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9";

/** The new schedule, chosen from three lists that always hold a value, then confirmed. */
export function ScheduleDrawer({
  detail,
  onClose,
  onDone,
}: {
  readonly detail: AutomationDetail;
  readonly onClose: () => void;
  readonly onDone: (told: string, fresh: AutomationDetail | null) => void;
}) {
  const start = detail.cadence ?? { every: "day", hourUtc: 8 };
  const [every, setEvery] = useState(start.every);
  const [weekday, setWeekday] = useState(start.weekday ?? 0);
  const [hour, setHour] = useState(start.hourUtc);
  const [reviewing, setReviewing] = useState(false);
  const everyId = useId();
  const dayId = useId();
  const hourId = useId();
  const chosen: CadenceFields = every === "week" ? { every, hourUtc: hour, weekday } : { every, hourUtc: hour };

  return (
    <>
      <Drawer
        open={!reviewing}
        onOpenChange={(open) => {
          if (!open) {
            onClose();
          }
        }}
        title={SCHEDULE_TITLE}
        description={detail.scheduleAccepts}
        footer={
          <>
            <Button variant="outline" onClick={onClose}>
              {KEEP_IT}
            </Button>
            <Button
              onClick={() => {
                setReviewing(true);
              }}
            >
              {REVIEW_SCHEDULE}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor={everyId} className="text-[13px] font-medium text-ink">
              {EVERY_LABEL}
            </label>
            <select
              id={everyId}
              className={SELECT}
              value={every}
              onChange={(event) => {
                setEvery(event.target.value);
              }}
            >
              {Object.entries(EVERY_WORDS).map(([value, words]) => (
                <option key={value} value={value}>
                  {words}
                </option>
              ))}
            </select>
          </div>
          {every === "week" ? (
            <div className="flex flex-col gap-1.5">
              <label htmlFor={dayId} className="text-[13px] font-medium text-ink">
                {DAY_LABEL}
              </label>
              <select
                id={dayId}
                className={SELECT}
                value={weekday}
                onChange={(event) => {
                  setWeekday(Number(event.target.value));
                }}
              >
                {detail.weekdays.map((name, index) => (
                  <option key={name} value={index}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          <div className="flex flex-col gap-1.5">
            <label htmlFor={hourId} className="text-[13px] font-medium text-ink">
              {HOUR_LABEL}
            </label>
            <select
              id={hourId}
              className={SELECT}
              value={hour}
              onChange={(event) => {
                setHour(Number(event.target.value));
              }}
            >
              {Array.from({ length: 24 }, (_, index) => (
                <option key={index} value={index}>
                  {`${String(index).padStart(2, "0")}:00`}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Drawer>
      {reviewing ? (
        <ChangeDialog
          detail={detail}
          act="reschedule"
          cadence={chosen}
          onClose={() => {
            setReviewing(false);
          }}
          onDone={onDone}
        />
      ) : null}
    </>
  );
}
