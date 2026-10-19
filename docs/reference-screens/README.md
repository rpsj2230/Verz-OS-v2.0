# Reference screenshots

The owner's reference screenshots, which console pages each one covers, and for each covered page what
was adapted and what was refused. They are compared and adapted, never copied: nothing in this folder
or in the console reproduces a reference screen's text or branding.

`index.json` is the record, and `console/tests/reference-screens.test.ts` is what holds it. It fails when

- a page the screenshots cover has no record;
- a record names a page the console's route table does not have, or a screenshot the index does not list;
- a record names a requirement that does not come from one of its screenshots (the register's `ANY-`
  rows name the screenshot each came from);
- a rejection the design keeps is contradicted by the page: **no single on and off adaptive learning
  switch**, and **no browser operator that rides the person's own session**.

## What is held and what is not

None of the thirteen images is in this folder yet, and none has ever been in this repository's history.
They live in the owner's workspace, outside the repository, and the session that built the index could
not read or copy them. `index.json` lists every image by its file name with `"file": null` and says why.

**What the owner supplies:** copy each image into this folder and set its `file` to the name it was
copied under. The test then requires the file to exist. The docs elsewhere say fourteen; the folder the
owner keeps them in holds thirteen, and the register names twelve of them, so one image has no
requirement behind it (`image-1788498461996`, which the register skips as `ANY-046`). If a fourteenth
exists, it is not in that folder.

## What has no record yet, and why

A screenshot whose `pages` is empty carries a `no_page_because`. The member application's screens (the
agent navigation, the agent chat, the task history) have no console page yet; the agent's People section
is not a section of the agent page yet. Each gets a record in the same commit as its page.

## Adding a record

A record is one console page, or one section of the agent page: its `address` as the route table
writes it, its `screenshots`, the `requirements` it answers, what it `adapted`, what it `refused` and
`why`. A section of `/agents/:agentId/:tab` names the tab. `not_yet` says plainly what the screenshot
shows that the page does not do yet.
