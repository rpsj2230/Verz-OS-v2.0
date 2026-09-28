/**
 * A document's Dashboard: what is recorded about it now, and what waits on the reader.
 *
 * Three cards and no more. Its review (the badge, the date, whether it is due, and Verify when the
 * API offered it), the reader's own open tasks on it, and where a request for the whole company has
 * got to. Each card says one thing and offers the one act that changes it; the figures across the
 * top are the header's and are not repeated here.
 *
 * Task ids: M27.15.40, M7.4.4, M7.4.6
 */

import { Link } from "react-router-dom";
import { Fact, FactList, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { WORKS_AT, type DocumentAct } from "./knowledgeActions";
import { dayWords, promotionWords, verifiedWords, type DocumentPage, type TaskRow } from "./knowledgeDocuments";
import { TaskList } from "./parts";

export const REVIEW_HEADING = "Review";
export const TASKS_HEADING = "Your tasks on this document";
export const COMPANY_HEADING = "Whole company";
export const NO_TASKS = "Nothing about this document is waiting for you.";

export function KnowledgeDashboard({
  page,
  tasks,
  offers,
  onAct,
  onChanged,
}: {
  readonly page: DocumentPage;
  readonly tasks: readonly TaskRow[];
  readonly offers: readonly DocumentAct[];
  readonly onAct: (act: DocumentAct) => void;
  readonly onChanged: () => void;
}) {
  const { document } = page;
  const promotion = promotionWords(document);
  const companyWide = document.level === "company";
  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-2">
      <SectionCard
        title={REVIEW_HEADING}
        action={
          offers.includes("verify") ? (
            <Button
              size="sm"
              variant="outline"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                onAct("verify");
              }}
            >
              Verify
            </Button>
          ) : undefined
        }
      >
        <FactList>
          <Fact label="Verification">{verifiedWords(document)}</Fact>
          <Fact label="Review by">{dayWords(document.reviewBy) ?? "Not set"}</Fact>
          <Fact label="Due now">{document.due ? "Yes" : "No"}</Fact>
        </FactList>
      </SectionCard>

      <SectionCard title={TASKS_HEADING}>
        {tasks.length === 0 ? <Note>{NO_TASKS}</Note> : <TaskList tasks={tasks} onChanged={onChanged} />}
      </SectionCard>

      <SectionCard
        title={COMPANY_HEADING}
        action={
          offers.includes("propose") ? (
            <Button
              size="sm"
              variant="outline"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                onAct("propose");
              }}
            >
              Ask for approval
            </Button>
          ) : undefined
        }
      >
        <FactList>
          <Fact label="Readable by everyone">{companyWide ? "Yes" : "No"}</Fact>
          {promotion === undefined ? null : (
            <Fact label="Your request">
              {promotion}
              {document.promotion?.status === "waiting" ? (
                <>
                  {" "}
                  <Link to={WORKS_AT.approvals} className="text-acc-text underline-offset-4 hover:underline">
                    Approvals
                  </Link>
                </>
              ) : null}
            </Fact>
          )}
        </FactList>
      </SectionCard>
    </div>
  );
}
