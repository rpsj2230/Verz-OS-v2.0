/**
 * One tool on the shared page kit: what it needs and does, where it is switched off, and the
 * switches this reader may throw, each confirmed.
 *
 * **The switches offered are the API's to decide.** `choicesFor` draws the install's switch only
 * when the answer says this reader may throw it and a department's only for the departments the
 * answer names; the route judges the press whatever was drawn.
 *
 * **Starting a tool again needs a reason and stopping one does not**, `brain.ops.halt`'s asymmetry;
 * the field says how long the reason must be before anything is sent.
 *
 * **Who switched a tool off is a principal id**, so it is in Advanced; the page says where and when.
 *
 * Task ids: M12.1.1, M12.1.3, M12.1.4, M12.3.8, M12.4.3, M27.16.1
 */

import { useId, useState, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  ConfirmDialog,
  DetailHeader,
  DetailPage,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  Note,
  SectionCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { when } from "../sessionsQuery";
import {
  choiceConsequence,
  choiceLabel,
  choiceQuestion,
  choicesFor,
  EFFECT_SENTENCES,
  EFFECT_WORDS,
  KEEP_IT,
  NO_LONGER_OFFERED,
  NOTE_LABEL,
  readChanged,
  readTools,
  REASON_LABEL,
  RUNG_WORDS,
  SENSITIVE_EFFECT_SENTENCES,
  switchBody,
  switchedSentence,
  switchPath,
  TOOLS_API_PATH,
  TOOLS_LABEL,
  UNREADABLE_ANSWER,
  type StopRow,
  type SwitchChoice,
  type ToolRow,
  type ToolsBody,
} from "../toolsQuery";
import { StatusChips } from "./ToolsPage";

export const READING_TOOL = "Reading this tool.";
export const NO_SUCH_TOOL = "No tool by that name is listed on this install.";
export const NOT_SWITCHED = "The tool was not switched";
export const SWITCHES_HEADING = "Switches";
export const SWITCHES_LEDE = "Stop it for the whole install or for one department's people. A stop can only narrow what agents may do.";

function where(stop: StopRow): string {
  return stop.department === null || stop.department === undefined ? "the install" : stop.department;
}

function ToolView({ row, body, onSwitched }: { readonly row: ToolRow; readonly body: ToolsBody; readonly onSwitched: (told: string) => void }) {
  const [confirming, setConfirming] = useState<SwitchChoice | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const reasonId = useId();
  const needed = body.reason_to_switch_on ?? 12;
  const choices = choicesFor(row, body);
  const stops = [...(row.off_for_install === null || row.off_for_install === undefined ? [] : [row.off_for_install]), ...row.stopped_for];
  const sensitive =
    row.sensitive_effect === null || row.sensitive_effect === undefined ? null : (SENSITIVE_EFFECT_SENTENCES[row.sensitive_effect] ?? row.sensitive_effect);

  function flip(choice: SwitchChoice): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(switchPath(choice.tool), { method: "POST", body: switchBody(choice, reason) });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setConfirming(null);
      setReason("");
      setFailure(null);
      onSwitched(switchedSentence(choice, readChanged(result.data) ?? true));
    })();
  }

  return (
    <DetailPage
      crumbs={[{ label: TOOLS_LABEL, to: "/tools" }, { label: row.name }]}
      header={
        <DetailHeader
          name={row.name}
          headingId="tool-heading"
          pills={
            <>
              <Chip>{EFFECT_WORDS[row.effect] ?? row.effect}</Chip>
              <StatusChips row={row} />
            </>
          }
          subline={`From ${row.source}`}
        />
      }
    >
      <div className="flex min-w-0 flex-col gap-4">
        <SectionCard title={SWITCHES_HEADING} lede={SWITCHES_LEDE}>
          {!row.registered ? (
            <Note kind="not-yet">{NO_LONGER_OFFERED}</Note>
          ) : choices.length === 0 ? (
            <Note>You may read this tool and not switch it.</Note>
          ) : (
            <div className="flex flex-wrap gap-2">
              {choices.map((choice) => (
                <Button
                  key={choice.department ?? "install"}
                  variant={choice.on ? "default" : "outline"}
                  size="sm"
                  className="min-h-11 sm:min-h-8"
                  disabled={busy}
                  aria-label={`${choiceLabel(choice)}: ${row.name}`}
                  onClick={() => {
                    setFailure(null);
                    setReason("");
                    setConfirming(choice);
                  }}
                >
                  {choiceLabel(choice)}
                </Button>
              ))}
            </div>
          )}
          {stops.length === 0 ? null : (
            <FactList className="mt-3">
              {stops.map((stop) => (
                <Fact key={`${where(stop)} ${stop.switched_off_at}`} label={`Off for ${where(stop)}`}>
                  Since {when(stop.switched_off_at)}.{stop.reason === null || stop.reason === undefined ? "" : ` Note: ${stop.reason}`}
                </Fact>
              ))}
            </FactList>
          )}
        </SectionCard>
        <SectionCard title="What it needs and does">
          <p className="m-0 mb-3 text-[13px] text-body">{row.description}</p>
          <FactList>
            <Fact label="Needs">
              <Chip mono>{row.capability}</Chip>
            </Fact>
            <Fact label="Effect">
              {EFFECT_SENTENCES[row.effect] ?? row.effect}
              {sensitive === null ? null : ` ${sensitive}`}
            </Fact>
            <Fact label="Result">{row.result_contract === "opaque" ? "Returned whole to those allowed it" : "Redacted field by field"}</Fact>
            <Fact label="Leash at most">{RUNG_WORDS[row.leash_at_most] ?? row.leash_at_most}</Fact>
            <Fact label="Runs as">{row.identity_mode === "service" ? "A shared service credential" : "The person asking"}</Fact>
          </FactList>
        </SectionCard>
        {stops.length === 0 ? null : (
          <Advanced>
            <FactList>
              {stops.map((stop) => (
                <Fact key={`${where(stop)} ${stop.switched_off_at}`} label={`Switched off for ${where(stop)} by`}>
                  <span className="font-mono text-[12px]">{stop.switched_off_by}</span>
                </Fact>
              ))}
            </FactList>
          </Advanced>
        )}
      </div>
      <ConfirmDialog
        open={confirming !== null}
        question={confirming === null ? "" : choiceQuestion(confirming)}
        consequence={confirming === null ? "" : choiceConsequence(confirming)}
        details={
          confirming === null ? undefined : (
            <div className="flex flex-col gap-2">
              <Label htmlFor={reasonId}>{confirming.on ? `${REASON_LABEL} (at least ${String(needed)} characters)` : NOTE_LABEL}</Label>
              <Textarea
                id={reasonId}
                name="reason"
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value);
                }}
              />
              {failure === null ? null : <FailureState failure={failure} title={NOT_SWITCHED} />}
            </div>
          )
        }
        confirmLabel={confirming === null ? "" : choiceLabel(confirming)}
        cancelLabel={KEEP_IT}
        busy={busy}
        onConfirm={() => {
          if (confirming !== null) {
            flip(confirming);
          }
        }}
        onCancel={() => {
          setConfirming(null);
          setReason("");
        }}
      />
    </DetailPage>
  );
}

export function ToolDetailPage({ name }: { readonly name: string }) {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const answer = useResource<unknown>(TOOLS_API_PATH, version);
  if (answer.busy) {
    return <LoadingState label={READING_TOOL} />;
  }
  const frame = (content: ReactNode) => (
    <div className="flex min-w-0 flex-col gap-4">
      <h1 className="m-0 font-heading text-[22px] font-semibold text-ink">{TOOLS_LABEL}</h1>
      {content}
    </div>
  );
  if (answer.failure !== null) {
    return frame(<FailureState failure={answer.failure} />);
  }
  const body = readTools(answer.data);
  if (body === null) {
    return frame(<Note>{UNREADABLE_ANSWER}</Note>);
  }
  const row = body.tools.find((one) => one.name === name);
  if (row === undefined) {
    return frame(<Note>{NO_SUCH_TOOL}</Note>);
  }
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {told === null ? null : (
        <div role="status">
          <Note kind="done">{told}</Note>
        </div>
      )}
      <ToolView
        row={row}
        body={body}
        onSwitched={(sentence) => {
          setTold(sentence);
          setVersion((count) => count + 1);
        }}
      />
    </div>
  );
}
