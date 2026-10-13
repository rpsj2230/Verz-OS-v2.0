"""The eight skills a new install can be furnished with, written as the files an import would carry.

M12.4.7 asks that an install hold a starter skill library: an SEO audit, keyword research, a
website health check, ticket analysis, complaint analysis, a monthly SEO report, proposal
generation and website troubleshooting, each approved, assignable and rehearsed against its
example tasks. This module is the declaration of the eight, and it argues three things.

**Each is a `SKILL.md` and nothing more privileged.** A starter skill is the text a person could
have pasted into the Skills screen, read back through `brain.console.skill_library.read_package`,
the one parser every way in goes through. It can say nothing a pasted file could not: no
capability, no scope, no executor, and no script, because a script needs a sandbox an install may
not run. So furnishing cannot widen anything, and an assignment of one is checked as any other.

**Each names only tools this product registers, and a test holds that.** A starter skill naming a
tool nobody registered would be a skill that could never do what it says, and the worst place to
learn that is an agent's first run. `tests/unit/test_starter_skills.py` builds the registry an
install builds and checks every name in every skill against it, and checks every example against
`brain.tools.skill_examples.examples_of`, so a tool renamed in a release is a failing test and not
a skill that stopped working on every install. The names are the website check, the knowledge
search and reading, and the connected sources' reads (a ticket, an invoice, a deal, search and
analytics figures, a domain, a DNS zone): the tools an install holds whether or not its owner has
connected the source, which is why a skill that needs a connected source says in its first step
what to do when there is no answer from it.

**None arrives approved.** A skill is the one part of an agent that comes from outside the
company, and an approval is a named person's statement about exact words. So these arrive as
undecided submissions of the product's first-run identity, and the person who reads one, rehearses
its examples and approves it is the person whose name the library records (needs-rupash 185, the
owner's to answer; this is its recommended option). Rejected: furnishing them approved by the
product, which would be a skill with no named approver on every install.

**Nothing here is a company's.** The wording speaks of a client, a site and a ticket, and names no
company, domain, person or price. Where a skill must be told something that differs between
companies, such as which price list or which report is the monthly one, it says to ask for it.

Scope: declaration. Nothing here opens a connection or reads a clock; the store that writes them is
`brain.ops.starter_skill_store`.

Task ids: M12.4.7
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: The first version of every starter skill.
STARTER_VERSION: Final = "1.0.0"


@dataclass(frozen=True)
class StarterSkill:
    """One starter skill: its name and the `SKILL.md` it is."""

    name: str
    markdown: str


def _skill(
    name: str,
    description: str,
    tools: tuple[str, ...],
    steps: tuple[str, ...],
    examples: tuple[tuple[str, tuple[str, ...]], ...],
) -> StarterSkill:
    lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
        f"version: {STARTER_VERSION}",
        f"tools: [{', '.join(tools)}]",
        "---",
        *steps,
        "",
        "## Examples",
        *(f"- {task} => {', '.join(expects)}" for task, expects in examples),
        "",
    ]
    return StarterSkill(name=name, markdown="\n".join(lines))


STARTER_SKILLS: Final[tuple[StarterSkill, ...]] = (
    _skill(
        "seo-audit",
        "Use when a person asks for an SEO audit of a client's site, or whether a site is "
        "set up to be found",
        (
            "knowledge.search_documents",
            "knowledge.read_document",
            "search_console.read_search_site",
            "website.check_site",
        ),
        (
            "1. Ask which site and which client the audit is for, and say if either is missing.",
            "2. Check the site with the website check and note the status, redirects and the "
            "days until the certificate expires.",
            "3. Read what Search Console reports for the site: queries, pages, clicks and "
            "indexing issues. If it gives nothing, say that the source is not connected or not "
            "granted, and go on with the rest.",
            "4. Search the knowledge library for the company's own SEO standard and read the "
            "document that matches. Hold the findings against it.",
            "5. Report in three parts: what is fine, what needs fixing and what could not be "
            "checked. Cite every figure to where it came from.",
        ),
        (
            (
                "Audit the SEO of the client's main site",
                (
                    "website.check_site",
                    "search_console.read_search_site",
                ),
            ),
            (
                "What does our SEO standard say about page titles",
                (
                    "knowledge.search_documents",
                    "knowledge.read_document",
                ),
            ),
            ("Is this site set up to be found", ("website.check_site",)),
        ),
    ),
    _skill(
        "keyword-research",
        "Use when a person asks which search terms a client's site should aim for, or what a "
        "site already ranks for",
        ("search_console.read_search_site", "knowledge.search_documents"),
        (
            "1. Ask which site, which service it sells and which place it sells in.",
            "2. Read what Search Console reports for the site and list the queries it already "
            "gets impressions for, with clicks and position.",
            "3. Separate the queries it ranks for from those it nearly ranks for, near the "
            "bottom of the first page or the top of the second.",
            "4. Search the knowledge library for the client's brief and the services they sell, "
            "and propose terms that match them and that the site does not yet rank for.",
            "5. Say which figures are the site's own and which are your suggestion. Never "
            "invent a search volume: if no source gave one, say none is available.",
        ),
        (
            ("What does the client's site already rank for", ("search_console.read_search_site",)),
            (
                "Suggest new keywords for the client's hosting page",
                (
                    "search_console.read_search_site",
                    "knowledge.search_documents",
                ),
            ),
            ("Which terms are we nearly ranking for", ("search_console.read_search_site",)),
        ),
    ),
    _skill(
        "website-health-check",
        "Use when a person asks whether a client's website is healthy, up and correctly configured",
        (
            "website.check_site",
            "domains.read_domain",
            "cloudflare.read_zone",
        ),
        (
            "1. Ask which site, and say if it is not one this person may check.",
            "2. Run the website check: status, redirects, certificate days left and response "
            "time. A site that does not answer is the first finding.",
            "3. Read the domain record for its registration and expiry, and the Cloudflare zone "
            "if the site is behind it. Say plainly when a source gave nothing.",
            "4. Give one line for each of: reachable, secure, domain current, protected. Mark "
            "each as fine, to watch or to fix.",
            "5. Name the single most urgent thing to do first.",
        ),
        (
            (
                "Is the client's website healthy",
                (
                    "website.check_site",
                    "domains.read_domain",
                ),
            ),
            ("When does the client's domain expire", ("domains.read_domain",)),
            ("Is the site behind Cloudflare and is the zone active", ("cloudflare.read_zone",)),
        ),
    ),
    _skill(
        "ticket-analysis",
        "Use when a person asks what a client's support tickets are about, how many are open "
        "or what keeps recurring",
        ("freshdesk.read_ticket", "knowledge.search_documents"),
        (
            "1. Ask which client and which period, and say if either is missing.",
            "2. Read the client's tickets for the period. If the helpdesk gives none, say that "
            "the source is not connected or not granted, and stop there.",
            "3. Group them by what they were about, and by status. Count each group.",
            "4. Search the knowledge library for the standard answer to each recurring group, "
            "and say which have one and which do not.",
            "5. Report what recurs, what is old and still open, and what a person should look "
            "at first. Quote a ticket by its reference, never from memory.",
        ),
        (
            ("What are the client's open tickets about", ("freshdesk.read_ticket",)),
            (
                "What problems keep recurring on the client's tickets",
                (
                    "freshdesk.read_ticket",
                    "knowledge.search_documents",
                ),
            ),
            (
                "Do we have a standard answer for the renewal tickets",
                ("knowledge.search_documents",),
            ),
        ),
    ),
    _skill(
        "complaint-analysis",
        "Use when a person asks about a client's complaint, how serious it is or what to say "
        "in reply",
        ("freshdesk.read_ticket", "hubspot.read_hubspot_company", "knowledge.search_documents"),
        (
            "1. Ask which client and which complaint, and say if the complaint cannot be found.",
            "2. Read the complaint's ticket and the client's earlier tickets, so the history "
            "is in front of you before any judgement.",
            "3. Read the client's company record for how long they have been a client and what "
            "they buy. Say if the source gave nothing.",
            "4. Search the knowledge library for the company's complaint policy and follow it.",
            "5. Say what the client is upset about in their own terms, how long it has run, "
            "whether it has happened before, and what the policy says to do. Draft a reply "
            "for a person to send; never send one.",
        ),
        (
            (
                "How serious is the client's complaint about downtime",
                (
                    "freshdesk.read_ticket",
                    "hubspot.read_hubspot_company",
                ),
            ),
            ("Has this client complained before", ("freshdesk.read_ticket",)),
            ("What does our complaint policy say to do", ("knowledge.search_documents",)),
        ),
    ),
    _skill(
        "monthly-seo-report",
        "Use when a person asks for a client's monthly SEO report, or to prepare the report "
        "for the month just ended",
        (
            "google_analytics.read_analytics_property",
            "search_console.read_search_site",
            "knowledge.search_documents",
            "knowledge.read_document",
        ),
        (
            "1. Ask which client and which month, and say if the month is not over.",
            "2. Read the analytics figures for the month and for the month before: visits, "
            "sources and the pages visited most.",
            "3. Read Search Console for the same two months: clicks, impressions, position and "
            "any indexing issue. Say when a source gave nothing, and do not fill the gap.",
            "4. Search the knowledge library for last month's report for this client and read "
            "it, so this one answers what that one promised.",
            "5. Write the report: what changed and why it probably did, what was done, what is "
            "planned next. Put every figure beside its previous month. Leave it for a person "
            "to review before it goes to the client.",
        ),
        (
            (
                "Prepare the client's monthly SEO report for last month",
                (
                    "google_analytics.read_analytics_property",
                    "search_console.read_search_site",
                ),
            ),
            (
                "What did last month's report for this client say",
                (
                    "knowledge.search_documents",
                    "knowledge.read_document",
                ),
            ),
            (
                "How did the client's search clicks change month on month",
                ("search_console.read_search_site",),
            ),
        ),
    ),
    _skill(
        "proposal-generation",
        "Use when a person asks for a proposal or a quotation for a prospective or existing client",
        (
            "hubspot.read_hubspot_deal",
            "local.read_price_list",
            "knowledge.search_documents",
            "knowledge.read_document",
        ),
        (
            "1. Ask who the proposal is for and what they asked for, and say if the deal cannot "
            "be found.",
            "2. Read the deal for what was discussed and agreed so far.",
            "3. Read the price list for each thing proposed. Use only prices it holds: if a "
            "price is not there, say so and leave it for a person to fill in.",
            "4. Search the knowledge library for the company's proposal template and the "
            "service descriptions, and read the ones that match. Follow the template.",
            "5. Draft the proposal for a person to review. It is never sent or issued by you: "
            "issuing a quotation is a person's act.",
        ),
        (
            (
                "Draft a proposal for the client's new website",
                (
                    "hubspot.read_hubspot_deal",
                    "local.read_price_list",
                ),
            ),
            ("What does the price list say for monthly maintenance", ("local.read_price_list",)),
            (
                "Which template do we use for a proposal",
                (
                    "knowledge.search_documents",
                    "knowledge.read_document",
                ),
            ),
        ),
    ),
    _skill(
        "website-troubleshooting",
        "Use when a person reports that a client's website is down, slow, showing a "
        "certificate warning or sending visitors to the wrong place",
        (
            "website.check_site",
            "domains.read_domain",
            "cloudflare.read_zone",
            "cloudflare.read_dns_record",
        ),
        (
            "1. Ask which site and what the person sees, in their words.",
            "2. Run the website check and say exactly what it found: status, redirects, "
            "certificate days left, response time.",
            "3. If it does not answer or redirects somewhere unexpected, read the domain record "
            "for an expired or changed registration, then the zone and its DNS records for a "
            "record that points somewhere it should not.",
            "4. Say what the evidence supports as the likely cause, and what it does not "
            "settle. Do not guess at a cause nothing read supports.",
            "5. Propose the fix as a step for a person. Changing DNS or anything on a live "
            "site is never done by you.",
        ),
        (
            (
                "The client's website is down, what is wrong",
                (
                    "website.check_site",
                    "domains.read_domain",
                ),
            ),
            (
                "Visitors are being sent to the wrong place",
                (
                    "website.check_site",
                    "cloudflare.read_dns_record",
                ),
            ),
            ("The browser warns about the site's certificate", ("website.check_site",)),
        ),
    ),
)
