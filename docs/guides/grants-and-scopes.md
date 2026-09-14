# Grants and scopes: a cookbook

Five worked examples of writing access, for whoever administers this system. Every example is
real. It uses the demo company's people, records and columns, and
`tests/unit/test_guide_docs.py` resolves every grant on this page with the product's own
resolver and asks every outcome of the product's own row plane. If the page and the product
ever disagree, that test fails, so what you read here is what the system does.

## How to read an example

Each example has two tables.

**The grants.** One row per grant: who holds it, the capability, the scope it applies in, and
when it ends. A capability is `verb:entity` for a whole row, or `verb:entity.column` for one
column, and `read:entity.*` for every column. A scope is a row filter, written as clauses joined
by `and`: `department = projects`, `department in projects, operations`, or
`reference starts with INV`. There is no `or` and no "except". Access is only ever added, and
it is taken away by deleting the grant that gave it. A holder written `agent <name>` is an
agent's ceiling rather than a person.

**Who reaches what.** One row per question: who is asking, whether directly or through an
agent, what they read, on which demo record, on which day, and whether they reach it or are
refused. A refusal and a record that does not exist look the same to the person asking. That
is deliberate, and nothing on a screen will tell them which it was.

The dates are in the year 2999 on purpose. An example that is about a grant expiring should not
also be about the day you happen to read it.

## A grant scoped to one department

The accounts lead holds every client column and every invoice column, in Accounts only. She
reaches Calderwood Estates, which is an Accounts client, and every invoice, which are Accounts
invoices. She is refused Brightpier Hotels, which is a Projects client, even though her
capability names every client column: the scope decides which rows, and the capability decides
which columns on those rows.

The two row grants (`read:client` and `read:invoice`) are there because reaching a row and
reading its columns are separate grants. The demo writes them for every person, and the third
example shows what happens without one.

<!-- checked: the grants in this example -->

| Holder | Capability | Scope | Until |
| --- | --- | --- | --- |
| `demo_accounts_lead` | `read:client.*` | `department = accounts` | no end |
| `demo_accounts_lead` | `read:invoice.*` | `department = accounts` | no end |
| `demo_accounts_lead` | `invoke:agent` | `department = accounts` | no end |
| `demo_accounts_lead` | `read:client` | `department = accounts` | no end |
| `demo_accounts_lead` | `read:invoice` | `department = accounts` | no end |

<!-- checked: who reaches what in this example -->

| Who | Through | Reads | Record | On | Outcome |
| --- | --- | --- | --- | --- | --- |
| `demo_accounts_lead` | directly | `read:client.name` | `demo_client_calderwood` | 2999-01-01 | reaches |
| `demo_accounts_lead` | directly | `read:invoice.amount_due` | `demo_invoice_10233` | 2999-01-01 | reaches |
| `demo_accounts_lead` | directly | `read:client` | `demo_client_brightpier` | 2999-01-01 | refused |
| `demo_accounts_lead` | directly | `read:client.name` | `demo_client_brightpier` | 2999-01-01 | refused |

**To write one:** give the capability, and set the scope to `department = <the department>`. If
the capability is a column or a wildcard, give the row read for that entity in the same scope as
well.

## A wildcard narrowed by an agent's ceiling

An agent is a lens, never a person. A run through an agent reaches what the person asking
reaches and what the agent's ceiling admits, and nothing either of them does not. The Projects
lead holds every client column in Projects. The agent `client_names` has a ceiling naming only
the client name, in Projects.

Asked directly, the lead reaches a Projects client's contract value. Asked through the agent,
the same person on the same record reaches the name and is refused the contract value, because
the ceiling does not name it. Through the agent she is also refused an Operations client, which
neither she nor the agent reaches.

A ceiling that names a column also admits the row that column is on, so the agent's ceiling
here does not need `read:client` written beside it. The product derives it, for read columns
only. A person's grants are not derived that way, which is why the lead's row grant is listed.

<!-- checked: the grants in this example -->

| Holder | Capability | Scope | Until |
| --- | --- | --- | --- |
| `demo_projects_lead` | `read:client.*` | `department = projects` | no end |
| `demo_projects_lead` | `read:job.*` | `department = projects` | no end |
| `demo_projects_lead` | `approve:envelope` | `department = projects` | no end |
| `demo_projects_lead` | `invoke:agent` | `department = projects` | no end |
| `demo_projects_lead` | `read:client` | `department = projects` | no end |
| `demo_projects_lead` | `read:job` | `department = projects` | no end |
| `agent client_names` | `read:client.name` | `department = projects` | no end |

<!-- checked: who reaches what in this example -->

| Who | Through | Reads | Record | On | Outcome |
| --- | --- | --- | --- | --- | --- |
| `demo_projects_lead` | directly | `read:client.contract_value` | `demo_client_brightpier` | 2999-01-01 | reaches |
| `demo_projects_lead` | `agent client_names` | `read:client.name` | `demo_client_brightpier` | 2999-01-01 | reaches |
| `demo_projects_lead` | `agent client_names` | `read:client.contract_value` | `demo_client_brightpier` | 2999-01-01 | refused |
| `demo_projects_lead` | `agent client_names` | `read:client` | `demo_client_ashgrove` | 2999-01-01 | refused |

**To write one:** decide what the agent needs, name exactly those columns in its ceiling, and
leave people's grants alone. Widening a person's grant does not widen what they reach through
the agent, and widening the agent's ceiling does not widen what any person reaches.

## Reaching a row and reading a column are two grants

A column grant on its own reaches nothing, because it never reaches a row to read the column
on. Somebody given only `read:client.contract_value` is refused the client and refused the
column. Add `read:client` in the same scope and the same column is reached. The row grant does
not carry any column with it: the second reviewer below reaches the row and the contract value,
and is refused the client's name, which nobody granted.

The holders here are invented for the example and are not people in the demo.

<!-- checked: the grants in this example -->

| Holder | Capability | Scope | Until |
| --- | --- | --- | --- |
| `column_only_reviewer` | `read:client.contract_value` | `department = operations` | no end |
| `row_and_column_reviewer` | `read:client.contract_value` | `department = operations` | no end |
| `row_and_column_reviewer` | `read:client` | `department = operations` | no end |

<!-- checked: who reaches what in this example -->

| Who | Through | Reads | Record | On | Outcome |
| --- | --- | --- | --- | --- | --- |
| `column_only_reviewer` | directly | `read:client` | `demo_client_ashgrove` | 2999-01-01 | refused |
| `column_only_reviewer` | directly | `read:client.contract_value` | `demo_client_ashgrove` | 2999-01-01 | refused |
| `row_and_column_reviewer` | directly | `read:client.contract_value` | `demo_client_ashgrove` | 2999-01-01 | reaches |
| `row_and_column_reviewer` | directly | `read:client.name` | `demo_client_ashgrove` | 2999-01-01 | refused |

**To write one:** grant the row read and the column reads together, in the same scope. A column
grant written narrower than its row grant is dropped from the query rather than applied row by
row, so keep the two scopes the same.

## A grant that expires

A grant can carry the moment it ends. Up to that moment it reaches what it names; from that
moment it reaches nothing, whatever else is still written in the grant table. The ending is
exclusive: a grant ending on 30 June 2999 has ended at midnight at the start of that day.

The visiting surveyor below is invented for the example. They may read Operations jobs until
the end of 29 June 2999.

<!-- checked: the grants in this example -->

| Holder | Capability | Scope | Until |
| --- | --- | --- | --- |
| `visiting_surveyor` | `read:job` | `department = operations` | 2999-06-30 |
| `visiting_surveyor` | `read:job.summary` | `department = operations` | 2999-06-30 |

<!-- checked: who reaches what in this example -->

| Who | Through | Reads | Record | On | Outcome |
| --- | --- | --- | --- | --- | --- |
| `visiting_surveyor` | directly | `read:job.summary` | `demo_job_2411` | 2999-06-29 | reaches |
| `visiting_surveyor` | directly | `read:job.summary` | `demo_job_2411` | 2999-06-30 | refused |
| `visiting_surveyor` | directly | `read:job.summary` | `demo_job_2418` | 2999-06-29 | refused |

**To write one:** set the end on every grant the person needs, rows and columns alike. A row
grant left without an end reaches rows after the column grants have ended, which is a person who
can still see that a record exists.

A contractor or a partner also carries an end on the person themselves, and the system refuses
to create one without it. That end applies to everything they hold, and the grant's own end
applies to that grant.

## Sees the client, never what it is worth

The demo's Projects coordinator needs to know which clients Projects works for, and must never
see what any of them is worth. She holds the client name and the client row, in Projects, and
nothing else about clients. She reaches Brightpier Hotels and its name, is refused its contract
value, and is refused Ashgrove Retail Group, which is an Operations client.

Nothing asked through an agent changes that. An agent whose ceiling names the contract value is
still refused it when she is the one asking, because a ceiling only ever narrows what the person
reaches.

<!-- checked: the grants in this example -->

| Holder | Capability | Scope | Until |
| --- | --- | --- | --- |
| `demo_projects_coord` | `read:client.name` | `department = projects` | no end |
| `demo_projects_coord` | `invoke:agent` | `department = projects` | no end |
| `demo_projects_coord` | `read:client` | `department = projects` | no end |
| `agent client_values` | `read:client.contract_value` | `department = projects` | no end |

<!-- checked: who reaches what in this example -->

| Who | Through | Reads | Record | On | Outcome |
| --- | --- | --- | --- | --- | --- |
| `demo_projects_coord` | directly | `read:client` | `demo_client_brightpier` | 2999-01-01 | reaches |
| `demo_projects_coord` | directly | `read:client.name` | `demo_client_brightpier` | 2999-01-01 | reaches |
| `demo_projects_coord` | directly | `read:client.contract_value` | `demo_client_brightpier` | 2999-01-01 | refused |
| `demo_projects_coord` | `agent client_values` | `read:client.contract_value` | `demo_client_brightpier` | 2999-01-01 | refused |
| `demo_projects_coord` | directly | `read:client` | `demo_client_ashgrove` | 2999-01-01 | refused |

**To write one:** name the columns the person needs, never the wildcard, and give the row read
beside them. Every column you leave out is withheld, and a column added to the source later is
withheld too until somebody grants it.

## What is checked and what is not

**Checked by `tests/unit/test_guide_docs.py`**, against the product rather than against a copy
of it:

| Claim | Against |
| --- | --- |
| Every outcome row: who reaches what, and who is refused | the product's resolver, its one intersection, and its row plane, over the demo's own records and column classification |
| Every capability that reads something names a row or a column the demo holds | the demo's column classification |
| Every demo person on this page holds exactly what the demo grants them | the demo's people |
| Every example states somebody reaching and somebody refused | the page itself |
| The five examples above are all present | the list the check carries |

**Not checked, and kept true by hand:** the sentences explaining each example, and every "To
write one" paragraph.

## Task ids

M34.3.2.2
