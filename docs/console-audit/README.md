# The console audit

What an administrator would need to manage, read out of the schema, the routes and the installation values, compared with what the console serves, screen by screen, with every gap either linked to its open leaf or recorded with its reason. It is the audit `docs/admin-console.md` asks for before the console is called done.

**These files are generated and must not be edited by hand.** `console/tests/console-audit.test.ts` renders them from `console/tests/support/consoleAudit.ts` and fails when any file here differs, or when a file here is one it did not render. To regenerate them after a change, run `npm run api:generate` and then `WRITE_CONSOLE_AUDIT=1 npx vitest run tests/console-audit.test.ts` in `console/`. The page at `/build/console-audit` is this file followed by every other file here in name order.

**One file per area, so two changes to the console meet only when they touch the same area.** Each area's file carries its own figures, and this index carries none that a change could move.

## What was measured

- The areas: the bullets of `docs/admin-console.md`, in its order, one file each.
- The tables, from `brain.db.Base.metadata`.
- The installation values, from `brain.install.INSTALLATION`.
- The routes under `/api/v1` and `/setup`, from the API's internal document.
- The console addresses, from every page's route file, `console/src/pages/*.route.tsx`, and `console/src/App.tsx`.
- The calls in the console that send a write, from `console/tests/support/writes.ts`, each followed to its routes.

## The rules every screen is held to

- **Loading, empty, unreachable and failed** are four different sentences on every registered address: `console/tests/screen-states.test.tsx`, with the addresses excused and why in `console/tests/support/screenStateRules.tsx`.
- **A destructive write is confirmed**, and the confirmation names what and says what will happen: `console/tests/destructive-confirmed.test.ts`, with the writes that are not destructive and why.
- **A form that writes is judged before it sends**, and a blank one says what to fill in: `console/tests/validated-before-write.test.tsx`.
- **Long lists page, search, filter and sort** through one convention, `brain.listing`, over the rows the reader may see, and a filter offers only values on rows drawn: `console/tests/long-lists.test.tsx` measures every long list against its route and records what each does not offer with its reason. Ending several sessions and deciding several review holdings are bulk acts, each item decided by the single act's own check.
- **Every write the console sends is followed to the system** (leaf `M27.8.17`): to the row it writes, to the audit entry it leaves, and to the behaviour it changes, each a named Python test or a reason there is none. Each area's file lists its own writes. A test marked database runs against a scratch Postgres, which CI provides.

## Area by area

- [People, roles, permissions and access control](01-people-roles-permissions-and-access-control.md)
- [Departments, teams and client configuration](02-departments-teams-and-client-configuration.md)
- [System settings and application configuration](03-system-settings-and-application-configuration.md)
- [AI providers, models and the routing between them](04-ai-providers-models-and-the-routing.md)
- [Agents and their configuration, including templates](05-agents-and-their-configuration-including-templates.md)
- [Skills and tools](06-skills-and-tools.md)
- [Workflows and automations](07-workflows-and-automations.md)
- [Connectors and third-party integrations](08-connectors-and-third-party-integrations.md)
- [API keys, credentials and secrets, held in the vault and never displayed](09-api-keys-credentials-and-secrets-held.md)
- [Knowledge bases, documents and data sources](10-knowledge-bases-documents-and-data-sources.md)
- [File and object storage](11-file-and-object-storage.md)
- [Prompts and system instructions](12-prompts-and-system-instructions.md)
- [Feature and module enablement](13-feature-and-module-enablement.md)
- [Notifications and email](14-notifications-and-email.md)
- [Webhooks](15-webhooks.md)
- [Scheduled jobs and background work](16-scheduled-jobs-and-background-work.md)
- [Usage, activity and system statistics](17-usage-activity-and-system-statistics.md)
- [Logs and errors](18-logs-and-errors.md)
- [The audit trail: who changed what, and when](19-the-audit-trail-who-changed-what.md)
- [System health and the state of every service](20-system-health-and-the-state-of.md)
- [Backup and recovery](21-backup-and-recovery.md)
- [Import and export](22-import-and-export.md)
- [Version, build and deployment information](23-version-build-and-deployment-information.md)
- [Not administered here](not-administered.md)
