/**
 * The page cases for `/ask` and `/ask/documents/:documentId`: the address each is mounted at and
 * what the stand-in API answers it with. `support/pageCases.ts` collects this file by its name and
 * says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // No answers, and `drawsValues` false, because this page asks nothing until somebody types
  // a question and presses a button: mounting it draws the form and the sentence saying
  // nothing has been asked. What it draws once an answer arrives is held to the same rules in
  // `tests/ask-page.test.tsx`, which can drive the asking this loop cannot.
  "/ask": { address: "/ask", signedIn: true, drawsValues: false, answers: {} },
  // The document a citation on Ask opens. The passage the link names is in the fragment, which
  // the harness does not send, so what is drawn is the document the API answered for the path.
  "/ask/documents/:documentId": {
    address: "/ask/documents/doc_handbook#chunk=doc_handbook.0001",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/knowledge/documents/doc_handbook": {
        document_id: "doc_handbook",
        title: UNBROKEN,
        passages: [
          {
            chunk_id: "doc_handbook.0001",
            section: UNBROKEN,
            text: UNBROKEN,
            updated_at: "2019-03-04T09:00:00Z",
          },
        ],
        truncated: false,
      },
    },
  },
};
