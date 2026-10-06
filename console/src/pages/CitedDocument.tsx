/**
 * The document a citation on the Ask screen opens, at the passage it cited.
 *
 * **A citation nobody can follow is a citation nobody checks.** The Ask screen links each document
 * citation here, with the passage's chunk in the address's fragment, and this page draws the
 * document's passages in reading order with that one marked, focused and scrolled to. A person
 * checking a claim reads the words it came from and the words around them, which is the whole of
 * what a citation is for. See `brain.gate.provenance`'s first paragraph.
 *
 * **Nothing here decides who may read the document.** The API reads it at the reader's own reach,
 * through the handler and the policy the answer used, and answers a withheld document and an
 * absent one with one 404, which is drawn in the API's own words and never explained. Four states
 * and four sentences: reading, the document, the API refusing, and an answer this page cannot
 * read.
 *
 * **The passage is found from the fragment, which no server sees.** See
 * `citedDocumentQuery.A_PASSAGE_IS_NAMED_IN_THE_FRAGMENT`. A passage that is not among those shown
 * is said in one sentence rather than left for the reader to hunt for.
 *
 * **A followed citation's place is sent back once, and nothing else is.** When the fragment names
 * the retrieval the answer was drawn from and the passage's place in the reader's list, the page
 * posts that place for the learning signal (M15.3.4). The chunk stays in the fragment; the request
 * carries a retrieval that names no document and a number, and its answer is not drawn.
 *
 * **No figure anywhere.** The passages are sections, not a numbered list, because a marker is a
 * number and a number here is a count of passages the reader was or was not shown.
 *
 * Task ids: M8.1.2, M15.3.4
 */

import { useEffect, useRef } from "react";
import { useLocation, useParams } from "react-router-dom";
import { request } from "../api/client";
import { useResource } from "../api/useResource";
import { FailureNotice } from "../ui/FailureNotice";
import {
  anchorOf,
  followedOf,
  retrievalUsesPath,
  CITED_DOCUMENT_LEDE,
  CITED_HERE,
  CITED_PASSAGE_GONE,
  CITED_PASSAGE_NOT_SHOWN,
  citedDocumentApiPath,
  MORE_THAN_SHOWN,
  NO_PASSAGES,
  readCitedDocument,
  READING_THE_DOCUMENT,
  UNREADABLE_DOCUMENT,
  UNTITLED,
} from "./citedDocumentQuery";

export function CitedDocument() {
  const { documentId = "" } = useParams();
  const { hash } = useLocation();
  const cited = anchorOf(hash);
  const answer = useResource<unknown>(documentId === "" ? null : citedDocumentApiPath(documentId));
  const document = answer.busy || answer.failure ? null : readCitedDocument(answer.data);
  const marked = useRef<HTMLElement | null>(null);
  const found = document !== null && document.passages.some((one) => one.chunkId === cited);

  // Once per address: the place of the passage followed, for the learning signal. What comes back
  // is not drawn, because a person reading a document has nothing to do with it.
  const followed = followedOf(hash);
  const sent = useRef("");
  useEffect(() => {
    if (followed === null || sent.current === hash) {
      return;
    }
    sent.current = hash;
    void request<unknown>(retrievalUsesPath(followed.retrievalId), {
      method: "POST",
      body: { position: followed.position },
    });
  }, [followed, hash]);

  // Once, when the passage the link named is on the screen: scroll to it and put focus on it, so
  // a keyboard or screen reader lands where a sighted reader's eye does.
  useEffect(() => {
    if (!found) {
      return;
    }
    marked.current?.scrollIntoView?.({ block: "start" });
    marked.current?.focus();
  }, [found]);

  if (answer.busy) {
    return (
      <article className="page">
        <p className="note" role="status">
          {READING_THE_DOCUMENT}
        </p>
      </article>
    );
  }
  if (answer.failure) {
    return (
      <article className="page">
        <FailureNotice failure={answer.failure} />
      </article>
    );
  }
  if (document === null) {
    return (
      <article className="page">
        <p className="note">{UNREADABLE_DOCUMENT}</p>
      </article>
    );
  }

  return (
    <article className="page">
      <h1>{document.title || UNTITLED}</h1>
      <p className="lede">{CITED_DOCUMENT_LEDE}</p>
      <p className="note">
        <code>{document.documentId}</code>
      </p>
      {cited !== "" && !found ? (
        <p className="note">{document.truncated ? CITED_PASSAGE_NOT_SHOWN : CITED_PASSAGE_GONE}</p>
      ) : null}
      {document.passages.length === 0 ? <p className="note">{NO_PASSAGES}</p> : null}
      {document.passages.map((one) => {
        const here = one.chunkId === cited;
        return (
          <section
            key={one.chunkId}
            ref={here ? marked : undefined}
            className={here ? "card cited__passage cited__passage--cited" : "card cited__passage"}
            tabIndex={here ? -1 : undefined}
            aria-current={here ? "location" : undefined}
          >
            {one.section !== "" ? <h2>{one.section}</h2> : null}
            {here ? <p className="cited__marker">{CITED_HERE}</p> : null}
            <p className="cited__text">{one.text}</p>
          </section>
        );
      })}
      {document.truncated ? <p className="note">{MORE_THAN_SHOWN}</p> : null}
    </article>
  );
}
