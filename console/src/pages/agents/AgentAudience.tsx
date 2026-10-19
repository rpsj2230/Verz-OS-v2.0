/**
 * Who an agent is offered to beside its level, on its Profile, and the confirmed acts that change it
 * (M27.11.13).
 *
 * **The rows are drawn from `GET /agents/{id}/audience` and from nothing else.** The route sends the
 * departments and people beside the level only to the agent's steward and to a holder of the
 * lifecycle authority, so for anybody else this draws no row at all: not an empty one saying nobody
 * was named, which would be a statement they were not told. A reader who is included is told so by
 * the availability facts above, which is the one fact they need.
 *
 * **Offering and withdrawing each go through `kit/ConfirmDialog`**, because an offer makes an agent
 * appear for people who did not see it and a withdrawal makes it disappear for people who did, and
 * `tests/destructive-confirmed.test.ts` reads both writes from their `onConfirm`. The add controls
 * are not a `<form>`: the offer button is disabled until a department is chosen or a name typed, and
 * the route judges the name again, so a blank cannot be sent from here and nothing is sent without
 * the dialog. A department is chosen from the install's own list, which the route sends only to a
 * reader who may change the offers; a person is typed as the People page shows their user id.
 *
 * **Why a change cannot be made is the route's sentence.** A holder of the authority who may not
 * change the offers (the switch is off, or the agent is personal or company-wide) is sent the
 * reason and sees it in place of the controls.
 *
 * Task ids: M27.11.13
 */

import { X } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Chip, ConfirmDialog, Fact, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { FailureNotice } from "../../ui/FailureNotice";
import { NativeSelect } from "../access/formParts";
import { readNotChanged } from "../agentLifecycleQuery";
import {
  agentAudienceApiPath,
  agentOfferApiPath,
  agentWithdrawApiPath,
  offerBody,
  readAudience,
  type OfferKind,
} from "./agentAudienceQuery";

export const ALSO_OFFERED_TO = "Also offered to";
export const NOT_OFFERED_FURTHER = "No other department or person.";
export const OFFER_IT_TO = "Offer it to";
export const CHOOSE_A_DEPARTMENT = "Choose a department";
export const A_PERSONS_ID = "Their user id, as the People page shows it.";
export const OFFER_LABEL = "Offer";
export const OFFER_QUESTION = (what: string): string => `Offer this agent to ${what}?`;
export const OFFER_CONSEQUENCE =
  "They will be shown this agent and may start it. It gives them access to nothing they could not already reach.";
export const WITHDRAW_QUESTION = (what: string): string => `Withdraw this agent from ${what}?`;
export const WITHDRAW_CONSEQUENCE =
  "They stop being shown this agent, unless its level still shows it to them. Anything they already started is not changed.";
export const AUDIENCE_NOT_CHANGED = "Nothing was changed";

interface Pending {
  readonly act: "offer" | "withdraw";
  readonly kind: OfferKind;
  readonly value: string;
}

interface Refused {
  readonly failure: ApiFailure;
  readonly sentence?: string;
}

/** How a department or a person is named in a sentence. */
export function whatIs(kind: OfferKind, value: string): string {
  return kind === "department" ? `the ${value} department` : `the person ${value}`;
}

export function AgentAudience({ agentId }: { readonly agentId: string }) {
  const kindId = useId();
  const valueId = useId();
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentAudienceApiPath(agentId), version);
  const shown = useMemo(() => (answer.data === null ? null : readAudience(answer.data)), [answer.data]);
  const [kind, setKind] = useState<OfferKind>("department");
  const [value, setValue] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [sending, setSending] = useState(false);
  const [refused, setRefused] = useState<Refused | null>(null);

  if (shown === null) {
    return null;
  }

  const confirm = () => {
    if (pending === null) {
      return;
    }
    const doing = pending;
    setSending(true);
    void (async () => {
      const path = doing.act === "offer" ? agentOfferApiPath(agentId) : agentWithdrawApiPath(agentId);
      const result = await request<unknown>(path, { method: "POST", body: offerBody(doing.kind, doing.value) });
      setSending(false);
      setPending(null);
      if (result.ok) {
        setValue("");
        setRefused(null);
        setVersion((count) => count + 1);
        return;
      }
      const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
      setRefused(notChanged === null ? { failure: result.failure } : { failure: result.failure, sentence: notChanged.sentence });
    })();
  };

  const offers: readonly { readonly kind: OfferKind; readonly value: string }[] = [
    ...shown.departments.map((one) => ({ kind: "department" as const, value: one })),
    ...shown.people.map((one) => ({ kind: "person" as const, value: one })),
  ];
  const chosen = value.trim();
  return (
    <>
      {shown.namesShown ? (
        <Fact label={ALSO_OFFERED_TO}>
          <div data-slot="agent-audience" className="flex min-w-0 flex-col gap-2">
            {refused === null ? null : (
              <FailureNotice
                failure={refused.failure}
                title={AUDIENCE_NOT_CHANGED}
                {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
              />
            )}
            {offers.length === 0 ? (
              <span className="text-dim">{NOT_OFFERED_FURTHER}</span>
            ) : (
              <ul aria-label={ALSO_OFFERED_TO} className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                {offers.map((one) => (
                  <li key={`${one.kind}:${one.value}`} className="inline-flex max-w-full items-center gap-1">
                    <Chip mono={one.kind === "person"}>{one.kind === "department" ? `${one.value} department` : one.value}</Chip>
                    {shown.mayChange ? (
                      <Button
                        variant="quiet"
                        size="icon-xs"
                        className="size-11 sm:size-6"
                        aria-label={`Withdraw this agent from ${whatIs(one.kind, one.value)}`}
                        disabled={sending}
                        onClick={() => {
                          setRefused(null);
                          setPending({ act: "withdraw", kind: one.kind, value: one.value });
                        }}
                      >
                        <X aria-hidden />
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
            <Note>{shown.words}</Note>
          </div>
          <ConfirmDialog
            open={pending !== null}
            question={pending === null ? "" : pending.act === "offer" ? OFFER_QUESTION(whatIs(pending.kind, pending.value)) : WITHDRAW_QUESTION(whatIs(pending.kind, pending.value))}
            consequence={pending?.act === "withdraw" ? WITHDRAW_CONSEQUENCE : OFFER_CONSEQUENCE}
            confirmLabel={pending?.act === "withdraw" ? "Withdraw it" : "Offer it"}
            cancelLabel="Not now"
            danger={pending?.act === "withdraw"}
            busy={sending}
            onConfirm={confirm}
            onCancel={() => {
              setPending(null);
            }}
          />
        </Fact>
      ) : null}
      {shown.mayChange ? (
        <Fact label={OFFER_IT_TO}>
          <div className="flex min-w-0 flex-wrap items-end gap-2">
            <div className="flex min-w-0 flex-col gap-1.5">
              <label htmlFor={kindId} className="text-[12px] text-dim">
                A department or a person
              </label>
              <NativeSelect
                id={kindId}
                describedBy=""
                invalid={false}
                value={kind}
                onChange={(next) => {
                  setKind(next === "person" ? "person" : "department");
                  setValue("");
                }}
              >
                <option value="department">A department</option>
                <option value="person">A person</option>
              </NativeSelect>
            </div>
            <div className="flex min-w-0 flex-col gap-1.5">
              <label htmlFor={valueId} className="text-[12px] text-dim">
                {kind === "department" ? CHOOSE_A_DEPARTMENT : A_PERSONS_ID}
              </label>
              {kind === "department" ? (
                <NativeSelect id={valueId} describedBy="" invalid={false} value={value} onChange={setValue}>
                  <option value="">{CHOOSE_A_DEPARTMENT}</option>
                  {shown.departmentChoices.map((one) => (
                    <option key={one} value={one}>
                      {one}
                    </option>
                  ))}
                </NativeSelect>
              ) : (
                <Input
                  id={valueId}
                  className="h-11 sm:h-9"
                  autoComplete="off"
                  value={value}
                  onChange={(event) => {
                    setValue(event.target.value);
                  }}
                />
              )}
            </div>
            <Button
              size="sm"
              className="min-h-11 sm:min-h-8"
              disabled={sending || chosen === "" || /\s/.test(chosen)}
              onClick={() => {
                setRefused(null);
                setPending({ act: "offer", kind, value: chosen });
              }}
            >
              {OFFER_LABEL}
            </Button>
          </div>
        </Fact>
      ) : shown.refusal === undefined ? null : (
        <Fact label="Offering it further">
          <Note>{shown.refusal}</Note>
        </Fact>
      )}
    </>
  );
}
