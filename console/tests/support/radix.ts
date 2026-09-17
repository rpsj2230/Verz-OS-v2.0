/**
 * The three element methods Radix calls that jsdom does not have, stubbed for the component tests.
 *
 * Radix's select captures the pointer on the trigger and scrolls the chosen option into view, and
 * jsdom implements neither, so without these the select throws on the first key press rather than
 * opening. The stubs do nothing and report no capture, which is the honest shape: there is no pointer
 * and no layout to scroll. Installed per test file that needs them rather than in `tests/setup.ts`,
 * so the rest of the suite runs against jsdom as it is.
 *
 * Task ids: none
 */

export function installRadixStubs(): void {
  const proto = globalThis.Element.prototype as Element & Record<string, unknown>;
  if (!("hasPointerCapture" in proto)) {
    proto.hasPointerCapture = () => false;
  }
  if (!("releasePointerCapture" in proto)) {
    proto.releasePointerCapture = () => {};
  }
  if (!("setPointerCapture" in proto)) {
    proto.setPointerCapture = () => {};
  }
  if (!("scrollIntoView" in proto)) {
    proto.scrollIntoView = () => {};
  }
}
