/**
 * Copying a text to the clipboard, answering whether the browser allowed it.
 *
 * **An answer, never an exception.** A browser without a clipboard, or one that refuses a page
 * permission to write to it, is the case a flow must still finish in, so each caller says "copied" or
 * shows the text to copy by hand, and neither path can be skipped by a throw nobody caught.
 *
 * Task ids: M11.9.4, M10.5.6
 */

/** Copy a text to the clipboard, answering whether the browser allowed it. */
export async function copied(text: string): Promise<boolean> {
  const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;
  if (clipboard === undefined) {
    return false;
  }
  try {
    await clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
