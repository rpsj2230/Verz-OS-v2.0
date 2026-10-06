/**
 * What Ask sends to attach a file to the conversation, and how the answer is read (M12.3.6).
 *
 * **A file is attached in two requests, each to the route that owns it.** The file is added as a
 * document at the person's own level by `POST /knowledge/uploads`, the same door the Knowledge
 * page uses, so it is scanned, read and kept where every document is and nobody else may read
 * it. Then `POST /threads/attachments` keeps that document on the person's thread, or opens one,
 * and answers the thread to continue with. Nothing here decides who may read the file: the
 * upload places it, and `chat.read_attachment` reads it at the asker's reach when they ask. See
 * `ATTACHING_IS_ADDING_A_DOCUMENT_ONLY_YOU_READ_AND_NAMING_IT_HERE`.
 *
 * Task ids: M12.3.6
 */

/** Written down because the obvious control would post the file to the thread itself. */
export const ATTACHING_IS_ADDING_A_DOCUMENT_ONLY_YOU_READ_AND_NAMING_IT_HERE =
  "A file attached here is added as a document only you may read, through the same checks every " +
  "document goes through, and then named on this conversation. An answer here reads it at your " +
  "reach; nobody else's conversation names it and nobody else may read it.";

/** Where a document is named on a thread, under the API base. */
export const ATTACHMENTS_API_PATH = "/threads/attachments";

/** The body that names one document on one thread, or on a new one when there is none yet. */
export function attachBody(
  threadId: string,
  attachmentId: string,
): { readonly thread_id: string | null; readonly attachment_id: string } {
  return { thread_id: threadId === "" ? null : threadId, attachment_id: attachmentId };
}

/** `brain.thread_routes.AttachedView`, as this console holds it. */
export interface Attached {
  readonly threadId: string;
  readonly attachmentId: string;
}

/** Read `AttachedView`, or null when the body is not one. */
export function readAttached(payload: unknown): Attached | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  if (typeof body.thread_id !== "string" || typeof body.attachment_id !== "string") {
    return null;
  }
  if (body.thread_id === "" || body.attachment_id === "") {
    return null;
  }
  return { threadId: body.thread_id, attachmentId: body.attachment_id };
}
