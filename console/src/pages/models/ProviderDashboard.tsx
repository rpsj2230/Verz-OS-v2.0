/**
 * A provider's Dashboard: the steps of the failover matrix that use it, its last test, and what it
 * has been sent.
 *
 * **Every line is from the providers answer the page already holds.** The steps are the plan the
 * next call makes, numbered from 1 in each level as the Routing page numbers them, with the role the
 * API derived and a marker only on a step that will not answer. What it has been sent is M5.6.4's
 * list: each kind of data by name with the number of calls that carried it, never the content.
 *
 * Task ids: M27.16.1, M5.6.4
 */

import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { FactList, Fact, Note, SectionCard } from "../../components/kit";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import {
  checkServedSentence,
  levelName,
  stepMarker,
  stepNumber,
  type CheckBody,
  type ProviderStateRow,
  type ProvidersBody,
} from "../modelsQuery";
import { WORKS_AT } from "./modelsActions";
import { MarkerPill, RolePill } from "./pills";
import { lastTestWords, stepsOf } from "./providerWords";

export const STEPS_HEADING = "Steps that use it";
export const STEPS_LEDE = "Where this provider sits on the failover matrix.";
export const NO_STEPS = "No step on the failover matrix uses this provider yet. Add one on the Routing page.";
export const LAST_TEST_HEADING = "Last test";
export const SENT_HEADING = "What it has been sent";
export const SENT_LEDE = "Each kind of data, with the number of calls that carried it. Counts are calls, not people.";
export const NOTHING_SENT = "Nothing has been sent to it on a step in the matrix now.";

export function ProviderDashboard({
  row,
  body,
  checked,
}: {
  readonly row: ProviderStateRow;
  readonly body: ProvidersBody;
  /** The test this page just sent, drawn with its outcome until the page is left. */
  readonly checked: CheckBody | null;
}) {
  const steps = stepsOf(row.provider, body.rungs);
  return (
    <div data-slot="provider-dashboard" className="flex min-w-0 flex-col gap-4">
      <SectionCard
        title={STEPS_HEADING}
        lede={STEPS_LEDE}
        action={
          <Link
            to={WORKS_AT.routing}
            className="inline-flex min-h-11 items-center gap-1 text-[13px] font-medium text-acc-text underline-offset-4 hover:underline sm:min-h-0"
          >
            Routing <ArrowUpRight aria-hidden className="size-3.5" />
          </Link>
        }
      >
        {steps.length === 0 ? (
          <Note>{NO_STEPS}</Note>
        ) : (
          <Table className="text-[13px]">
            <TableCaption className="sr-only">{STEPS_HEADING}</TableCaption>
            <TableHeader className="bg-sunk">
              <TableRow className="hover:bg-transparent">
                <TableHead scope="col">Complexity</TableHead>
                <TableHead scope="col">Step</TableHead>
                <TableHead scope="col">Model</TableHead>
                <TableHead scope="col">Role</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {steps.map((step) => {
                const marker = stepMarker(step);
                return (
                  <TableRow key={step.rung_id}>
                    <TableCell>{levelName(step.tier)}</TableCell>
                    <TableCell className="tabular-nums">{String(stepNumber(step, body.rungs))}</TableCell>
                    <TableCell className="font-mono text-[12px] [overflow-wrap:anywhere] whitespace-normal">{step.model}</TableCell>
                    <TableCell>
                      <span className="flex flex-wrap items-center gap-1.5">
                        <RolePill role={step.role} />
                        {marker === null ? null : <MarkerPill marker={marker} />}
                      </span>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </SectionCard>

      <SectionCard title={LAST_TEST_HEADING}>
        <FactList>
          <Fact label="Last test">{lastTestWords(row.last_check)}</Fact>
          {row.last_check?.model === null || row.last_check?.model === undefined ? null : (
            <Fact label="Model used">
              <span className="font-mono text-[12px]">{row.last_check.model}</span>
            </Fact>
          )}
        </FactList>
        {checked === null ? null : (
          <div role="status" className="mt-3 flex flex-col gap-1">
            <Note kind={checked.answered ? "done" : "info"}>{checked.told}</Note>
            {checked.answered ? <Note>{checkServedSentence(checked)}</Note> : null}
          </div>
        )}
      </SectionCard>

      <SectionCard title={SENT_HEADING} lede={SENT_LEDE}>
        {row.disclosed.length === 0 ? (
          <Note>{NOTHING_SENT}</Note>
        ) : (
          <FactList>
            {row.disclosed.map((one) => (
              <Fact key={one.category} label={one.told}>
                <span className="tabular-nums">{one.attempts.toLocaleString("en-GB")}</span>
              </Fact>
            ))}
          </FactList>
        )}
      </SectionCard>
    </div>
  );
}
