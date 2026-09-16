/// <reference types="vite/client" />

/**
 * The bundler's ambient types, for the CSS imports in `main.tsx` and the components, and
 * for nothing else.
 *
 * This file used to declare the two build-time settings the console read. It declares none
 * now, because the console reads none: Vite compiles such a value into the bundle as plain
 * text, and this product ships one image to every company that installs it, so a compiled-in
 * issuer is an image only the company it was built for can use. The issuer, the client id
 * and the API base arrive at runtime from `/api/console.js`; see `src/config.ts` and
 * `src/brain/console_static.py`.
 *
 * The reference above stays because the stylesheet imports need it. Removing the
 * declarations rather than emptying them is deliberate: an empty interface reads as a list
 * somebody is meant to add to, and `tests/config.test.tsx` refuses the whole mechanism
 * across `src/` rather than trusting a declaration to be kept in step.
 */
