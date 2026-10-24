/**
 * The name of the global `/api/console.js` assigns, on its own so a module that only needs the
 * served document can read it without evaluating `config.ts`.
 *
 * **Why it is not in `config.ts`.** `config.ts` reads the document the moment it is first imported
 * and freezes what it found. A page module that imported it only to learn this name would make every
 * page, and every test that names a page's constants, evaluate the configuration before the
 * document exists in a test, and the console would report itself unconfigured. The spelling is a
 * fact about `brain.console_static.CONSOLE_CONFIG_GLOBAL`, and `config.ts` re-exports it so the
 * test that holds the two together reads it from where it always did.
 *
 * Task ids: M35.1.1.1
 */

export const CONFIG_GLOBAL = "__BRAIN_CONFIG__";
