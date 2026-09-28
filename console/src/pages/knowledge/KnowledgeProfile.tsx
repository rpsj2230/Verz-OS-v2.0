/**
 * A document's Profile: its record, its text, and the identifiers in Advanced.
 *
 * **The text is asked for only when somebody opens it**, from the passages route, which answers a
 * reader whose own read admits this version and refuses an administrator who adds documents without
 * reading them. So the card is drawn only when the history says this version is readable, and the
 * passages are redacted exactly as an answer's are. **Identifiers are in Advanced and nowhere else**:
 * the document's reference, the steward's person id and the version it replaced.
 *
 * Task ids: M27.15.40, M27.16.1, M7.4.5
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { Advanced, Fact, FactList, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { passagesPath } from "../knowledgeLifecycleQuery";
import {
  dayWords,
  documentAddress,
  levelWords,
  promotionWords,
  stateWords,
  verifiedWords,
  type DocumentPage,
} from "./knowledgeDocuments";

export const DETAILS_HEADING = "Details";
export const TEXT_HEADING = "Text";
export const SHOW_TEXT = "Show the text";
export const LOADING_TEXT = "Loading the text.";
export const NO_TEXT = "Nothing in this version is yours to read.";

interface Passage {
  readonly ordinal: number;
  readonly section: string;
  readonly text: string;
}

function readPassages(payload: unknown): { readonly passages: readonly Passage[]; readonly truncated: boolean } {
  const body = typeof payload === "object" && payload !== null ? (payload as Record<string, unknown>) : {};
  const passages = (Array.isArray(body["passages"]) ? (body["passages"] as readonly unknown[]) : []).flatMap((one) => {
    const row = typeof one === "object" && one !== null ? (one as Record<string, unknown>) : {};
    return typeof row["ordinal"] === "number" && typeof row["text"] === "string"
      ? [{ ordinal: row["ordinal"], section: typeof row["section"] === "string" ? row["section"] : "", text: row["text"] }]
      : [];
  });
  return { passages, truncated: body["truncated"] === true };
}

function Passages({ itemId }: { readonly itemId: string }) {
  const answer = useResource<unknown>(passagesPath(itemId));
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy) {
    return <LoadingState label={LOADING_TEXT} rows={3} />;
  }
  const { passages, truncated } = readPassages(answer.data);
  if (passages.length === 0) {
    return <Note>{NO_TEXT}</Note>;
  }
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {passages.map((one) => (
        <div key={one.ordinal} className="flex min-w-0 flex-col gap-1">
          {one.section === "" ? null : <p className="m-0 text-[12px] font-medium text-dim">{one.section}</p>}
          <p className="m-0 text-[13px] leading-relaxed whitespace-pre-wrap text-ink [overflow-wrap:anywhere]">{one.text}</p>
        </div>
      ))}
      {truncated ? <Note>The text is longer than one reading shows; the first part is above.</Note> : null}
    </div>
  );
}

export function KnowledgeProfile({ page }: { readonly page: DocumentPage }) {
  const { document, versions } = page;
  const [reading, setReading] = useState(false);
  const readable = versions.find((one) => one.itemId === document.itemId)?.readable === true;
  const replaced = document.supersedes === undefined ? undefined : versions.find((one) => one.itemId === document.supersedes);
  const promotion = promotionWords(document);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title={DETAILS_HEADING}>
        <FactList>
          <Fact label="Type">{document.kindLabel ?? "Not recorded"}</Fact>
          <Fact label="Visible to">{levelWords(document.level)}</Fact>
          <Fact label="Department">{document.department ?? "None"}</Fact>
          <Fact label="Steward">{document.stewardName ?? (document.youSteward ? "You" : "Not named")}</Fact>
          <Fact label="State">{stateWords(document.state)}</Fact>
          <Fact label="Verification">{verifiedWords(document)}</Fact>
          <Fact label="Review by">{dayWords(document.reviewBy) ?? "Not set"}</Fact>
          <Fact label="Added">{dayWords(document.addedAt) ?? "Not recorded"}</Fact>
          {replaced === undefined ? null : (
            <Fact label="Replaces">
              <Link to={documentAddress(replaced.itemId)} className="text-acc-text underline-offset-4 hover:underline">
                {replaced.title}
              </Link>
            </Fact>
          )}
          {document.solves === undefined ? null : <Fact label="Solves">{document.solves}</Fact>}
          {promotion === undefined ? null : <Fact label="Whole company">{promotion}</Fact>}
        </FactList>
      </SectionCard>

      {readable ? (
        <SectionCard
          title={TEXT_HEADING}
          action={
            reading ? undefined : (
              <Button
                size="sm"
                variant="outline"
                className="min-h-11 sm:min-h-8"
                onClick={() => {
                  setReading(true);
                }}
              >
                {SHOW_TEXT}
              </Button>
            )
          }
        >
          {reading ? <Passages itemId={document.itemId} /> : <Note>The passages answers are drawn from, as you may read them.</Note>}
        </SectionCard>
      ) : null}

      <Advanced>
        <FactList>
          <Fact label="Reference">
            <code className="font-mono text-[12px]">{document.itemId}</code>
          </Fact>
          {document.stewardId === undefined ? null : (
            <Fact label="Steward id">
              <code className="font-mono text-[12px]">{document.stewardId}</code>
            </Fact>
          )}
          {document.supersedes === undefined ? null : (
            <Fact label="Replaces">
              <code className="font-mono text-[12px]">{document.supersedes}</code>
            </Fact>
          )}
        </FactList>
      </Advanced>
    </div>
  );
}
