/**
 * What the undo page a weekly learning digest links asks the API for. No React.
 *
 * **The digest's undo is the person's own, on their sign-in alone.** `brain.mine_routes`'
 * `LEARNING_UNDO_PATH` takes a memory's id and nothing naming a person, decides the memory was
 * formed from the caller's own words, and refuses anybody else's as a memory that does not exist.
 * It asks for no grant, so the link works for everybody the digest is sent to, where Forget on My
 * workspace opens only on the member grant.
 *
 * Task ids: M16.5.1
 */

/** Where the undo is posted. `brain.mine_routes.LEARNING_UNDO_PATH`. */
export const LEARNING_UNDO_API_PATH = "/me/learning/undo";

/** The page's own address, with the memory's id after it. `brain.learning_told.UNDO_PATH`. */
export const UNDO_PAGE_PREFIX = "/me/undo/";

/** The body an undo sends: the memory's id and nothing else, as `MineMemoryAsked` declares. */
export function undoBody(memoryId: string): { readonly memory_id: string } {
  return { memory_id: memoryId };
}
