/**
 * One breach case: when the clock started and why, what the case owes and by when, what is wrong
 * with it, and each step recorded from here, read out of the cases answer so a case the reader may
 * not see is the same one sentence as one that does not exist.
 *
 * **The steps are offered in the order the law runs them and only while they are open**: the
 * assessment until it is made, each notification until it is recorded, a decision not to notify the
 * individuals until they are notified or it is filed. Closing is offered when the case says it is
 * closable, and otherwise its button is drawn inert with the route's own sentence saying why.
 *
 * Task ids: M24.2.4, M27.16.1
 */

import { History } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  DetailHeader,
  DetailPage,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  PageHeader,
  SectionCard,
  StatCard,
  UnavailableAction,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { subjectAddress } from "../auditQuery";
import {
  BASIS_LABELS,
  BREACHES_API_PATH,
  GROUND_LABELS,
  isOpen,
  labelOf,
  obligationSentence,
  SOURCE_LABELS,
  type BreachesAnswer,
} from "../complianceQuery";
import { nameOf, peopleIn, whenWords } from "../review/parts";
import {
  ASSESS_LABEL,
  CLOSE_LABEL,
  COMMISSION_LABEL,
  EXCEPTION_FORM_LABEL,
  INDIVIDUALS_LABEL,
  StepDrawer,
  useClose,
  type Step,
} from "./ComplianceActs";
import { CaseStatePill, COMPLIANCE_HEADING, READING_COMPLIANCE, viewAddress, VIEW_LABELS } from "./CompliancePage";

export const NO_CASE = "No breach case here";
export const NO_CASE_MORE = "The Breach cases view lists every case you may see.";

function Case({ caseId, onDone, told, version }: { readonly caseId: string; readonly onDone: (told: string) => void; readonly told: string | null; readonly version: number }) {
  const [step, setStep] = useState<Step | null>(null);
  const answer = useResource<BreachesAnswer>(BREACHES_API_PATH, version);
  const trail = [{ label: COMPLIANCE_HEADING, to: viewAddress("breaches") }, { label: VIEW_LABELS.breaches, to: viewAddress("breaches") }];
  const one = answer.data?.cases.find((found) => found.case_id === caseId);
  const closing = useClose(
    one ?? ({ case_id: caseId, evidence_reference: "" } as NonNullable<typeof one>),
    onDone,
  );

  if (answer.failure !== null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <PageHeader crumbs={trail} title={VIEW_LABELS.breaches} />
        <FailureState failure={answer.failure} />
      </div>
    );
  }
  if (answer.data === null) {
    return <LoadingState label={READING_COMPLIANCE} />;
  }
  if (one === undefined) {
    return (
      <PageHeader
        crumbs={[...trail, { label: NO_CASE }]}
        title={NO_CASE}
        lede={NO_CASE_MORE}
        actions={
          <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
            <Link to={viewAddress("breaches")}>{VIEW_LABELS.breaches}</Link>
          </Button>
        }
      />
    );
  }
  const people = peopleIn(answer.data);
  const open = isOpen(one);
  const excused = one.exception_ground !== null;
  const steps: { readonly step: Step; readonly label: string; readonly offered: boolean }[] = [
    { step: "assessment", label: ASSESS_LABEL, offered: one.assessed_at === null },
    { step: "commission", label: COMMISSION_LABEL, offered: one.commission_notified_at === null },
    { step: "individuals", label: INDIVIDUALS_LABEL, offered: one.individuals_notified_at === null && !excused },
    { step: "exception", label: EXCEPTION_FORM_LABEL, offered: one.individuals_notified_at === null && !excused },
  ];

  return (
    <DetailPage
      crumbs={[...trail, { label: one.evidence_reference }]}
      header={
        <>
          <DetailHeader
            name={`Breach case ${one.evidence_reference}`}
            headingId={`case-${one.case_id}`}
            pills={<CaseStatePill one={one} />}
            actions={
              <>
                <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
                  <Link to={subjectAddress("breach", one.case_id)}>
                    <History aria-hidden /> History
                  </Link>
                </Button>
                {open ? (
                  one.closable ? (
                    <Button size="sm" variant="destructive" className="min-h-11 sm:min-h-8" disabled={closing.busy} onClick={closing.ask}>
                      {CLOSE_LABEL}
                    </Button>
                  ) : (
                    <UnavailableAction label={CLOSE_LABEL} text={CLOSE_LABEL} reason={answer.data.closing} />
                  )
                ) : null}
              </>
            }
            figures={
              <KpiStrip label="This case's clock" count={4}>
                <StatCard label="Clock started" value={whenWords(one.clock_starts_at)} />
                <StatCard label="Assessment" value={one.assessed_at === null ? "Not yet made" : whenWords(one.assessed_at)} />
                <StatCard label="Commission notified" value={one.commission_notified_at === null ? "Not recorded" : whenWords(one.commission_notified_at)} />
                <StatCard
                  label="Individuals notified"
                  value={one.individuals_notified_at === null ? (excused ? "Not to be notified" : "Not recorded") : whenWords(one.individuals_notified_at)}
                />
              </KpiStrip>
            }
          />
          {told === null ? null : (
            <div role="status">
              <Note kind="works">{told}</Note>
            </div>
          )}
          {closing.drawn}
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-4">
        {open ? (
          <SectionCard title="Record a step" lede="Each is recorded once, as yours, and cannot be taken back.">
            <div className="flex flex-wrap gap-2">
              {steps
                .filter((one) => one.offered)
                .map((one) => (
                  <Button key={one.step} variant="outline" size="sm" className="min-h-11 sm:min-h-8" onClick={() => setStep(one.step)}>
                    {one.label}
                  </Button>
                ))}
            </div>
          </SectionCard>
        ) : null}
        {one.obligations.length === 0 ? null : (
          <SectionCard title="What it owes">
            <ul aria-label="What this case owes" className="m-0 flex list-disc flex-col gap-1 pl-5 text-[13px] text-body">
              {one.obligations.map((duty) => (
                <li key={duty.kind} className={duty.overdue ? "text-crit" : undefined}>
                  {obligationSentence(duty, whenWords)}
                </li>
              ))}
            </ul>
          </SectionCard>
        )}
        {one.findings.length === 0 ? null : (
          <SectionCard title="What is wrong with it">
            <ul aria-label="What is wrong with this case" className="m-0 flex list-disc flex-col gap-1 pl-5 text-[13px] text-warn">
              {one.findings.map((finding) => (
                <li key={finding}>{finding}</li>
              ))}
            </ul>
          </SectionCard>
        )}
        <SectionCard title="The case">
          <FactList>
            <Fact label="Became aware">
              {`${whenWords(one.became_aware_at)}, ${one.awareness_basis === "estimated" ? "an estimate" : "observed"}, from ${labelOf(SOURCE_LABELS, one.awareness_source).toLowerCase()}`}
            </Fact>
            <Fact label="Recorded by">{nameOf(people, one.recorded_by)}</Fact>
            <Fact label="Evidence">{one.evidence_reference}</Fact>
            <Fact label="Assessment">
              {one.assessed_at === null
                ? "Not yet made."
                : `${one.significant_harm === true ? "Likely" : "Not likely"} to result in significant harm; ${one.affected_count === null ? "the number affected is not yet established" : `${String(one.affected_count)} affected`}.`}
            </Fact>
            {one.exception_ground === null ? null : <Fact label="Not notifying the individuals">{labelOf(GROUND_LABELS, one.exception_ground)}</Fact>}
            {one.closed_at === null ? null : <Fact label="Closed">{`${whenWords(one.closed_at)}${one.closed_by === null ? "" : `, by ${nameOf(people, one.closed_by)}`}`}</Fact>}
          </FactList>
          <p className="m-0 mt-3 text-[12px] text-dim">{`Deadlines are ${labelOf(BASIS_LABELS, "statutory")} or ${labelOf(BASIS_LABELS, "guideline")}, as each line says.`}</p>
        </SectionCard>
        <Advanced>
          <FactList>
            <Fact label="Case">
              <code>{one.case_id}</code>
            </Fact>
            <Fact label="Recorded by">
              <code>{one.recorded_by}</code>
            </Fact>
          </FactList>
        </Advanced>
      </div>
      {step === null ? null : (
        <StepDrawer
          one={one}
          step={step}
          onClose={() => setStep(null)}
          onDone={(sentence) => {
            setStep(null);
            onDone(sentence);
          }}
        />
      )}
    </DetailPage>
  );
}

export function BreachPage({ caseId }: { readonly caseId: string }) {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const onDone = useCallback((sentence: string) => {
    setTold(sentence);
    setVersion((count) => count + 1);
  }, []);
  return <Case caseId={caseId} onDone={onDone} told={told} version={version} />;
}
