"""Turning an observed name into a comparison key, and refusing to when the key would lie.

`brain.resolution.canonical` keeps every observed name form verbatim, because a table holding
only normalised forms cannot be re-normalised when the normalisation changes. This is the
normalisation, and it is the half of entity resolution where damage is quiet: **the cascade
merges two records because their keys are equal, so every rule here that makes two different
strings equal is a rule that can make two different companies one company.** A wrong merge is
not a wrong answer, it is a permission surface joined to another permission surface, which is
the failure `canonical` is shaped against.

So each step is argued separately, and the ones that lose information say what they lose.

**Suffix stripping is the dangerous half and it is deliberately narrow.** "ABC Pte Ltd" and
"ABC Ltd" normalise together, which is almost always right. "Ace Co" and "Ace" normalise
together too, which is less obviously right and is the same rule. Three properties bound it.
Suffixes come off the *end* only, so "Pte Ltd Trading" keeps its first two tokens. They come
off as whole *tokens*, never as substrings, so "Incorporated Systems" keeps its "Inc" and
"Sincere Trading" keeps its "inc"; substring stripping is the classic implementation and it
mangles ordinary words. And a name that is entirely suffix tokens is not stripped at all, so
"Pte Ltd" does not become the empty string, because an empty key is equal to every other empty
key and joins every degenerate row in the estate to every other. See
`SUFFIX_STRIPPING_IS_WHERE_TWO_COMPANIES_BECOME_ONE` and
`A_NAME_THAT_IS_ENTIRELY_A_SUFFIX_IS_NOT_A_NAME`.

Both keys survive on the result. `collapsed` is the name with everything done to it except
suffix stripping, `key` is the same with the suffixes off, and they are carried separately so
that a caller can tell "these two agreed on their full names" from "these two agreed only
after their legal forms were removed". M14.3.2 asks the second to be corroborated by a further
field; nothing here does that, and there would be nowhere to record the distinction if the two
forms had been collapsed into one value.

**A short name goes to a person, and that is not an error.** A real company is called IBM,
DBS or SIA. Under `MIN_KEY_CHARS` characters the key is still computed and still returned; what
changes is the verdict, and the verdict routes it to review rather than into the cascade. See
`A_SHORT_NAME_IS_NOT_A_BAD_NAME`.

**Accent folding is done here so that it is done once (M14.2.4).** The phrase in the leaf is
"via an immutable wrapper so it can be indexed", and the trap it names is specific. PostgreSQL
declares `unaccent()` STABLE rather than IMMUTABLE, on purpose, because its behaviour depends
on a dictionary file that can be reloaded while the server is running. An expression index
requires IMMUTABLE, so indexing `unaccent(name)` either refuses to build or, wrapped
carelessly, builds an index that goes stale in silence the day somebody edits the rules. The
wrapper is written down in `IMMUTABLE_UNACCENT_SQL` together with what it costs, which is that
IMMUTABLE there is a promise the author makes and the server does not check. See
`AN_IMMUTABLE_WRAPPER_IS_A_PROMISE_THE_SERVER_DOES_NOT_CHECK`.

**The Python fold and the PostgreSQL one are not proven to agree, and this is said plainly
because a normalisation that differs between the index and the query is a match that silently
never fires.** `unicodedata.normalize("NFKD", ...)` removes combining marks, so it folds every
letter that decomposes into a base plus an accent. It does nothing at all to the Latin letters
that do not decompose, and there are several that matter in a client list: U+00F8, U+0142,
U+00E6, U+0111, U+00FE. Postgres's `unaccent.rules` maps several of those, because it is a
lookup table rather than a decomposition. `NON_DECOMPOSING_LATIN` closes the gap for the ones
we can name, and closing part of a gap is not closing it: nothing in this repository compares
the two implementations, and no test can, because there is no server in a unit test. The
failure when they differ is one-directional and quiet. The index holds one folding, the query
computes another, the join misses, and two records that are one company stay two, with nothing
reporting it. It is a false negative, which is the safe direction, and the names it drops are
Nordic and Central European ones, which makes it a systematic gap rather than a random one.

**The discipline that removes the problem rather than managing it: fold in Python, store the
key in an ordinary column, index the column.** Then one implementation computes the fold, once,
at write time, and the expression-index question never arises. The wrapper is for the case
where an expression index over a column nobody may add is the only option, and that case should
be argued for rather than reached for. `ACCENT_FOLD_ID` exists so a stored key can record which
fold produced it: a key stamped with an id the running fold no longer has is detectably stale,
where an unstamped one is silently stale.

**Nothing here is installed in PostgreSQL.** `IMMUTABLE_UNACCENT_SQL` is a string in a Python
module. No migration in this repository creates that function, no index uses it, and no column
stores a key produced here. See `NOTHING_HERE_IS_INSTALLED_IN_POSTGRES`, which is a constant so
that claiming otherwise means deleting it.

**The UEN validator validates the shapes and does not check the check character (M14.2.6).**
ACRA publishes the three formats and does not publish the check-digit algorithm. Several
mutually inconsistent implementations circulate. Implementing a guessed one would reject valid
UENs, and a rejected UEN in this system is a real client falling out of stage one of the
cascade into a weaker stage, silently and in the direction nobody looks. So the check character
is validated as being a letter in the right position and nothing further, and
`UenCheck.check_character_verified` is a field that can only ever be False, so the limit
travels with every answer rather than living in a comment. See
`THE_CHECK_CHARACTER_IS_NOT_VALIDATED`.

Rejected: normalising inside `canonical.identifier_hash`. That function deliberately normalises
nothing, and the reason it gives is the reason this module exists as a separate one: two
implementations of normalisation produce two sets of digests, and the day they disagree the
entities stop joining and nothing reports it.

Rejected: deleting punctuation rather than replacing it with a space. Deleting is better for
"A.B.C", which becomes "abc" instead of "a b c". It is fatal for suffix stripping, because
"ABC Pte.Ltd." would become one token "abcpteltd" and no whole-token rule can find a suffix
inside it. Token boundaries are what make the safe form of suffix stripping possible at all, so
punctuation becomes a boundary, and the cost is that "A.B.C" and "ABC" no longer agree.

Scope: domain logic. Nothing here opens a connection, reads a clock or touches a table. The
year ceiling a UEN is checked against is a parameter for the reason `canonical` takes its
timestamps as parameters.

Task ids: M14.2.1, M14.2.2, M14.2.3, M14.2.4, M14.2.5, M14.2.6
"""

from __future__ import annotations

import enum
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Final

# ------------------------------------------------------------------ written-down reasons
#: Why suffix stripping is bounded to the end, to whole tokens, and to leaving something behind.
SUFFIX_STRIPPING_IS_WHERE_TWO_COMPANIES_BECOME_ONE = (
    "Every rule that makes two different strings equal can make two different companies one "
    "company, and suffix stripping is the rule that does the most of it. Three bounds hold "
    "it. Only at the end, because 'Pte Ltd Trading' is a name and not a legal form. Only as "
    "whole tokens, because substring stripping turns 'Incorporated Systems' into 'orporated "
    "Systems' and quietly rewrites 'Sincere' as well. And never to nothing, because the empty "
    "key is equal to every other empty key. What is left after those three is still lossy: "
    "'Ace Co' and 'Ace' become one key, and whether that is right depends on facts this "
    "module does not have. So the unstripped form is carried beside the stripped one, and "
    "M14.3.2 asks for a second field before a name-only agreement is believed."
)

#: Why a name made only of legal forms is not stripped at all.
A_NAME_THAT_IS_ENTIRELY_A_SUFFIX_IS_NOT_A_NAME = (
    "Stripping 'Pte Ltd' leaves the empty string, and the empty string is equal to the empty "
    "string, so every row whose name was nothing but a legal form joins every other one and "
    "the resulting entity is a bag of unrelated companies. The guard is not a length check "
    "afterwards, which is what an author reaches for and which still admits a key of one "
    "letter: the strip itself refuses to remove the last token, so the key is the observed "
    "form, and the verdict sends it to a person. A row like that is a data-entry failure "
    "somewhere upstream and a person is the only thing that can say which company it meant."
)

#: Why three characters is a review and not a refusal.
A_SHORT_NAME_IS_NOT_A_BAD_NAME = (
    "IBM, DBS, SIA and UOB are real companies with three-letter names, so a minimum-length "
    "rule that refused them would refuse the estate's largest counterparties first. The guard "
    "does not refuse and does not discard: the key is computed, the key is returned, and the "
    "verdict routes it to a human instead of into the cascade. The figure is four because a "
    "key of three characters has one trigram that is not built out of the padding, and a "
    "similarity score over one trigram is a coincidence rather than a measurement."
)

#: What an IMMUTABLE wrapper around a STABLE function actually buys, and what it costs.
AN_IMMUTABLE_WRAPPER_IS_A_PROMISE_THE_SERVER_DOES_NOT_CHECK = (
    "PostgreSQL declares unaccent() STABLE rather than IMMUTABLE because its behaviour "
    "depends on a dictionary that can be reloaded while the server runs, and an expression "
    "index requires IMMUTABLE. Wrapping it in a function the author declares IMMUTABLE makes "
    "the index buildable and does not make the underlying behaviour immutable: the label is "
    "an assertion the planner trusts and never verifies. The day somebody edits "
    "unaccent.rules and reloads, every index built on the wrapper holds the old folding while "
    "every new query computes the new one, and the two stop meeting. Nothing errors. The "
    "discipline is therefore to treat the rules file as part of the schema, to change it only "
    "in a migration, and to REINDEX everything built on the wrapper in that same migration. "
    "The design that avoids needing the discipline is to fold in the application, store the "
    "key in an ordinary column and index the column."
)

#: Why the two foldings are described rather than reconciled.
THE_TWO_FOLDINGS_ARE_NOT_PROVEN_TO_AGREE = (
    "unicodedata's NFKD fold removes combining marks and therefore folds every letter that "
    "decomposes. It does nothing to Latin letters that do not decompose, and Postgres's "
    "unaccent.rules maps several of those because it is a lookup table rather than a "
    "decomposition. NON_DECOMPOSING_LATIN closes the gap for the letters we can name, which "
    "is not the same as closing it, and no unit test can compare the two because there is no "
    "server in one. The failure mode is worth stating exactly: the index holds one folding, "
    "the query computes another, the join misses, and two records that are one company stay "
    "two with nothing reporting it. That is a false negative, which is the safe direction, "
    "and it falls on Nordic and Central European names rather than at random."
)

#: What is installed and what is still not, kept as a constant so a change has to edit it.
NOTHING_HERE_IS_INSTALLED_IN_POSTGRES = (
    "Migration 0021 installs IMMUTABLE_UNACCENT_SQL and builds one expression index over it, "
    "so the wrapper is no longer only a string in a Python module. Three things are still not "
    "installed and the distinction matters. No column anywhere stores a key this module "
    "computed, so the fold that runs at write time is still Python's and the fold in the index "
    "is still Postgres's, which is the divergence THE_TWO_FOLDINGS_ARE_NOT_PROVEN_TO_AGREE "
    "describes. No query in this repository uses that index, because the match cascade has no "
    "caller. And no deployment has run the migration, so the IMMUTABLE label has been checked "
    "by a table in this file rather than by a server. That is said in a constant rather than "
    "in a comment so that a later claim to the contrary requires deleting the sentence."
)

#: Why the check character of a UEN is not validated.
THE_CHECK_CHARACTER_IS_NOT_VALIDATED = (
    "ACRA publishes the three UEN formats and does not publish the check-digit algorithm. "
    "Several mutually inconsistent implementations circulate and none of them is "
    "authoritative. A validator that implemented a guessed one would reject valid UENs, and a "
    "rejected UEN here is a real client falling out of stage one of the cascade into a weaker "
    "stage, quietly. So the last character is checked for being a letter in the right "
    "position and for nothing else, and check_character_verified is a field that cannot be "
    "set to True, so a caller reading a UenCheck is told the limit rather than assuming there "
    "is none."
)


# ------------------------------------------------------------------------- the accent fold
#: Latin letters that carry no combining mark and therefore survive an NFKD fold untouched.
#:
#: Each entry is a letter whose ASCII rendering is conventional rather than derived: U+00F8
#: becomes "o" because that is how the name is spelled in an English-language client list, not
#: because anything decomposes it. Every line names its letter in words as well, because a
#: reviewer reading a diff of this table cannot tell U+0142 from U+006C at a glance and the
#: table is a list of pairs of characters that look alike.
#:
#: Deliberately short. Every entry is a place where two spellings become one key, so the list
#: is the letters that actually appear in a Singapore agency's client names, not every letter
#: Unicode has. Adding one re-normalises the whole estate, which is why `ACCENT_FOLD_ID`
#: changes when it changes.
NON_DECOMPOSING_LATIN: Mapping[str, str] = MappingProxyType(
    {
        "\u00f8": "o",  # latin small letter o with stroke
        "\u0111": "d",  # latin small letter d with stroke
        "\u00f0": "d",  # latin small letter eth
        "\u00fe": "th",  # latin small letter thorn
        "\u0142": "l",  # latin small letter l with stroke
        "\u00e6": "ae",  # latin small letter ae
        "\u0153": "oe",  # latin small ligature oe
        "\u0127": "h",  # latin small letter h with stroke
        "\u0167": "t",  # latin small letter t with stroke
        "\u0131": "i",  # latin small letter dotless i
    }
)


def _fold_id(mapping: Mapping[str, str]) -> str:
    """A short digest naming one folding, so a stored key can say which one made it.

    Derived from the rule table rather than typed, because a hand-maintained version string is
    a version string somebody forgets to bump, and the forgetting is invisible: the index keeps
    the id it was built with and the fold quietly starts producing something else.

    Twelve hex characters. This is a change detector and not a security boundary, so the
    question is whether two rule tables collide by accident, and forty-eight bits is far beyond
    the handful of revisions a rule table sees in its life.
    """
    material = "\n".join(f"{key}={value}" for key, value in sorted(mapping.items()))
    return sha256(f"nfkd-mn-drop\n{material}".encode()).hexdigest()[:12]


#: Which folding produced a key. Stamped onto every `NormalisedName`.
ACCENT_FOLD_ID: Final = _fold_id(NON_DECOMPOSING_LATIN)


#: The wrapper M14.2.4 asks for, written down rather than installed.
#:
#: Two details are the whole of it. The two-argument form of `unaccent` names the dictionary
#: explicitly as a `regdictionary`, so the result does not depend on `search_path`; the
#: one-argument form does, which is one of the two reasons the built-in is STABLE. And the
#: IMMUTABLE label is asserted by whoever writes this and checked by nothing. See
#: `AN_IMMUTABLE_WRAPPER_IS_A_PROMISE_THE_SERVER_DOES_NOT_CHECK` for what that costs and for
#: the design that does not need it.
IMMUTABLE_UNACCENT_SQL: Final = """\
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE OR REPLACE FUNCTION er.immutable_unaccent(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$;
"""


class Volatility(enum.StrEnum):
    """PostgreSQL's three volatility categories, spelled as `pg_proc.provolatile` spells them.

    A `StrEnum` over the catalogue's own single letters rather than over readable words, so the
    day somebody checks this table against a running server the comparison is against the value
    the server returns and not against a translation of it.
    """

    IMMUTABLE = "i"
    STABLE = "s"
    VOLATILE = "v"


#: What PostgreSQL declares about each function an index expression here may name, keyed by the
#: name and the number of arguments it was called with.
#:
#: **Keyed by arity because the arity is the whole trap.** `to_tsvector('english', body)` takes
#: a `regconfig` and is IMMUTABLE; `to_tsvector(body)` reads `default_text_search_config` and is
#: only STABLE, so PostgreSQL refuses it in a generated column outright. 0009 is the migration
#: that hit this and its header records both halves. A table keyed by name alone would give one
#: answer for two functions that behave differently, and the answer it gave would be the
#: permissive one for whichever form was written down.
#:
#: **`unaccent` is STABLE in both forms and that is deliberate on PostgreSQL's part**, because
#: the dictionary behind it can be reloaded while the server runs. That is the fact this whole
#: section exists for, it is what 0009 says makes `to_tsvector('english', unaccent(body))`
#: refused, and it is why `IMMUTABLE_UNACCENT_SQL` exists at all.
#:
#: Written down rather than queried, because a unit test has no server. That is a real limit
#: and it is the one `NOTHING_HERE_IS_INSTALLED_IN_POSTGRES` names: this table is a copy of the
#: catalogue and nothing has compared the two. What makes it more than an opinion is that
#: `indexable` is run over the expressions migration 0021 actually indexes, and over the
#: expression 0009 independently records as refused, so the table has to agree with a statement
#: made elsewhere in this repository rather than only with itself.
PG_VOLATILITY: Mapping[tuple[str, int], Volatility] = MappingProxyType(
    {
        ("er.immutable_unaccent", 1): Volatility.IMMUTABLE,
        ("lower", 1): Volatility.IMMUTABLE,
        ("upper", 1): Volatility.IMMUTABLE,
        ("btrim", 1): Volatility.IMMUTABLE,
        ("to_tsvector", 2): Volatility.IMMUTABLE,
        ("to_tsvector", 1): Volatility.STABLE,
        ("unaccent", 1): Volatility.STABLE,
        ("unaccent", 2): Volatility.STABLE,
        ("public.unaccent", 1): Volatility.STABLE,
        ("public.unaccent", 2): Volatility.STABLE,
        ("now", 0): Volatility.STABLE,
        ("random", 0): Volatility.VOLATILE,
    }
)

#: A function call inside a SQL expression: an optionally schema-qualified lowercase name
#: followed by an open bracket. The lookbehind is what stops the tail of a qualified name being
#: read as a second call of its own.
_CALL_RE: Final = re.compile(r"(?<![A-Za-z0-9_.])([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*)\s*\(")


def _argument_count(expression: str, open_at: int) -> int:
    """How many arguments the bracket at `open_at` encloses.

    Commas at depth one, plus one, and nought for an empty bracket. Quoted literals are skipped
    whole, because a comma inside `'a,b'` is not an argument separator and counting it would
    give a function the wrong arity, which is how a STABLE function gets looked up as its
    IMMUTABLE namesake.
    """
    depth = 1
    commas = 0
    seen_content = False
    index = open_at + 1
    while index < len(expression) and depth > 0:
        character = expression[index]
        if character == "'":
            seen_content = True
            index += 1
            while index < len(expression):
                if expression[index] == "'":
                    if index + 1 < len(expression) and expression[index + 1] == "'":
                        index += 2
                        continue
                    break
                index += 1
        elif character == "(":
            depth += 1
            seen_content = True
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 1:
            commas += 1
        elif not character.isspace():
            seen_content = True
        index += 1
    return commas + 1 if seen_content else 0


def calls_in(expression: str) -> tuple[tuple[str, int], ...]:
    """Every function call in a SQL expression, as a name and an arity, outermost first.

    Scanned rather than parsed with a SQL grammar, which is a real limit: this understands
    brackets, quotes and names, and would read a cast written as `cast(x as text)` as a call to
    something named `cast`. That failure is in the safe direction, because a name this module
    has no volatility for is refused rather than assumed immutable.
    """
    found: list[tuple[str, int]] = []
    index = 0
    while index < len(expression):
        if expression[index] == "'":
            index += 1
            while index < len(expression):
                if expression[index] == "'":
                    if index + 1 < len(expression) and expression[index + 1] == "'":
                        index += 2
                        continue
                    break
                index += 1
            index += 1
            continue
        match = _CALL_RE.match(expression, index)
        if match is None:
            index += 1
            continue
        open_at = match.end() - 1
        found.append((match.group(1).lower(), _argument_count(expression, open_at)))
        index = open_at + 1
    return tuple(found)


def indexable(expression: str) -> tuple[str, ...]:
    """Every reason PostgreSQL would refuse to index this expression (M14.2.4).

    An expression index and a stored generated column both require every function in the
    expression to be IMMUTABLE, and that requirement is the reason this module has a wrapper at
    all. The check is written against `PG_VOLATILITY`, which is what the server declares, rather
    than against the wrapper, so it refuses `unaccent` and admits `er.immutable_unaccent` for
    the reason PostgreSQL does and not because one of them is ours.

    An unlisted function is refused. Assuming immutability for an unknown name is the failure
    this whole check exists to prevent, and the cost of refusing is that somebody adding a
    function to an index has to add a line here saying what the server thinks of it.

    Empty for an expression with no function calls in it at all: a bare column is indexable and
    always was. See `AN_IMMUTABLE_WRAPPER_IS_A_PROMISE_THE_SERVER_DOES_NOT_CHECK` for what the
    wrapper does not buy.
    """
    findings: list[str] = []
    for name, arity in calls_in(expression):
        declared = PG_VOLATILITY.get((name, arity))
        if declared is None:
            findings.append(
                f"{name} with {arity} argument(s) has no declared volatility here, and an "
                "unlisted function is refused rather than assumed immutable"
            )
        elif declared is not Volatility.IMMUTABLE:
            findings.append(
                f"{name} with {arity} argument(s) is {declared.name}, and an index expression "
                "requires IMMUTABLE; wrap it in a function that declares itself so, and treat "
                "the wrapped behaviour as part of the schema"
            )
    return tuple(findings)


def accent_fold(text: str) -> str:
    """Strip accents, in the order that makes the two halves cover each other.

    The named map runs first and the decomposition second. That way round because a mapped
    letter can carry an accent of its own, and running NFKD afterwards removes it; the other
    order would leave the mark stranded on a replacement the map had already made.

    Combining marks are dropped by category rather than by an allowlist. `Mn` is exactly the
    set NFKD produces when it separates a letter from its accent, so dropping the category is
    the fold, and listing individual marks would be a shorter list that silently keeps the
    unlisted ones.
    """
    mapped = "".join(NON_DECOMPOSING_LATIN.get(ch, ch) for ch in text)
    decomposed = unicodedata.normalize("NFKD", mapped)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


# ------------------------------------------------------- case, whitespace and punctuation
#: Apostrophes, which are deleted where every other mark becomes a space.
#:
#: An apostrophe inside a word is a letter-level mark rather than a token boundary: "O'Brien"
#: is one word and "o brien" is two, and the second does not agree with "OBrien" while the
#: first does not agree with anything at all. The straight and curly forms are both here
#: because a name copied out of a document carries the curly one and a name typed into a form
#: carries the straight one, and those are the same company.
APOSTROPHES: Final = frozenset(
    {
        "'",  # apostrophe
        "\u2019",  # right single quotation mark
        "\u2018",  # left single quotation mark
        "\u02bc",  # modifier letter apostrophe
        "\u00b4",  # acute accent
        "`",  # grave accent
    }
)

#: Unicode general categories that become a token boundary.
#:
#: Every punctuation class and every symbol class. Symbols are included because "&" is
#: punctuation and "+" is a maths symbol and no reader of a company name thinks of those as
#: different kinds of thing. The cost is stated rather than hidden: "A&B" and "A B" produce one
#: key, so a firm named for two partners agrees with an unrelated pair of initials.
_BOUNDARY_CATEGORIES: Final = frozenset(
    {"Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po", "Sm", "Sc", "Sk", "So"}
)

#: Format characters: zero-width space, zero-width joiner, the byte-order mark and their
#: relatives. Deleted rather than made into a boundary, because they are invisible: a name
#: carrying one looks identical to the same name without it, and turning it into a space would
#: split a word on a character nobody can see. `str.isspace()` is False for all of them, which
#: is why a whitespace collapse alone does not catch them and why this is a separate rule.
_FORMAT_CATEGORY: Final = "Cf"


def collapse(text: str) -> str:
    """Case fold, accent fold, drop the invisibles, punctuate into spaces, collapse the runs.

    **There are two case folds and each has a different job.** The first version of this
    docstring said the first fold was there because casefold maps U+00DF to "ss" where NFKD
    does not, and a mutation run disproved it: replacing the first fold with `str.lower`
    changed no key, because the second fold maps that letter anyway. What the first one
    actually does is put the text into the form `NON_DECOMPOSING_LATIN` is keyed in, which is
    lower case. Without it, U+00D8 in a name written in capitals never meets the map, comes
    through NFKD untouched because it has no combining mark, and reaches the key as itself,
    where Postgres's rules file would have folded it to "o". That is exactly the silent
    disagreement between the two implementations this module is written to narrow.

    The second fold is for what NFKD produces rather than for what it is given. A compatibility
    decomposition expands U+2121 to "TEL" and U+216B to "XII", both in capitals, and a key that
    differs by case is a key that does not join.

    `str.casefold` rather than `str.lower` at both sites, and that one is about U+00DF, which
    lower leaves alone in both positions.

    Whitespace collapse is `split` and `join`, which uses Python's own whitespace definition
    and therefore covers the non-breaking space and the ideographic space without a list of
    them. The zero-width characters it does not cover are removed above, by category.
    """
    folded = accent_fold(text.casefold())
    kept: list[str] = []
    for ch in folded:
        if ch in APOSTROPHES:
            continue
        category = unicodedata.category(ch)
        if category == _FORMAT_CATEGORY:
            continue
        kept.append(" " if category in _BOUNDARY_CATEGORIES else ch)
    return " ".join("".join(kept).split()).casefold()


# ------------------------------------------------------------------------ suffix stripping
#: The legal forms M14.2.3 names, one token each.
#:
#: Exactly the leaf's list and deliberately no more. "Pte Ltd" and "Sdn Bhd" are two tokens
#: apiece and need no phrase entry, because the strip runs repeatedly from the end. What is
#: absent is as deliberate: no Corp, no Pty, no GmbH, no BV, no Incorporated. Every addition
#: re-normalises every name already stored and merges pairs that were separate the day before,
#: so the set is the one somebody specified rather than the one an author thought of, and
#: growing it is a migration rather than an edit.
SUFFIX_TOKENS: frozenset[str] = frozenset(
    {"pte", "ltd", "limited", "sdn", "bhd", "inc", "llc", "co"}
)


def strip_suffixes(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Remove trailing legal forms. Returns what is kept and what came off, in order.

    Repeated from the end, so "abc pte ltd" loses both tokens without a phrase table. Whole
    tokens only: nothing here does a substring test, which is what keeps "incorporated" and
    "sincere" intact.

    **Nothing is removed when removing everything is the result.** The check is on the outcome
    rather than on the input, so it catches "co" as well as "pte ltd", and the caller gets the
    observed tokens back unchanged with an empty removal list. See
    `A_NAME_THAT_IS_ENTIRELY_A_SUFFIX_IS_NOT_A_NAME`.
    """
    kept = list(tokens)
    removed: list[str] = []
    while kept and kept[-1] in SUFFIX_TOKENS:
        removed.insert(0, kept.pop())
    if not kept:
        return tokens, ()
    return tuple(kept), tuple(removed)


# --------------------------------------------------------------------- the length guard
#: The fewest trigrams over which a similarity score is a measurement rather than a
#: coincidence.
#:
#: Two. With one, "similarity" is the presence or absence of a single shared substring, and
#: every key sharing it scores identically against every other, so the stage-three band that
#: M14.3.3 puts between two thresholds has nothing in it to be between.
MIN_TRIGRAMS_FOR_A_MEASUREMENT: Final = 2

#: Under this many characters, a normalised name goes to a person instead of into the cascade.
#:
#: Four, and the four is arithmetic rather than taste. A key of n characters contains n - 2
#: trigrams that are not built out of the padding pg_trgm adds at the ends, and the padded ones
#: are the same for every key sharing a first or last letter, so they measure the padding. Two
#: real trigrams therefore needs four characters. Written as a literal rather than as the sum,
#: so a test can check the derivation against the figure it comes from instead of recomputing
#: it and comparing the answer with itself.
MIN_KEY_CHARS: Final = 4


class NameVerdict(enum.StrEnum):
    """What may be done with a normalised name.

    One member means "use it" and the rest mean "ask a person", and they are separate members
    rather than one REVIEW because the three reach a reviewer as three different questions.
    Too short is "is this initialism the client you think it is". Entirely a suffix is "which
    company was meant here". Nothing left is "this field held punctuation".
    """

    #: Long enough, and not made only of legal forms. The only value the cascade may use.
    USABLE = "usable"
    #: Shorter than `MIN_KEY_CHARS`. A real company can be called IBM.
    TOO_SHORT = "too short"
    #: Every token is a legal form, so nothing was stripped and there is no name underneath.
    ENTIRELY_A_SUFFIX = "entirely a suffix"
    #: Punctuation, whitespace or invisibles, and no letters or digits at all.
    NOTHING_LEFT = "nothing left"


#: The verdicts that send a name to a person.
#:
#: Written out rather than derived as "everything except USABLE", for the reason
#: `brain.memory.tiers.CHANGES_WHAT_ANYBODY_MAY_SEE` is written out: derived, the set and the
#: rule would agree by construction and a test comparing them would move both sides together.
#: Written out, adding a verdict without deciding which side it falls on fails a test.
ROUTES_TO_REVIEW: frozenset[NameVerdict] = frozenset(
    {NameVerdict.TOO_SHORT, NameVerdict.ENTIRELY_A_SUFFIX, NameVerdict.NOTHING_LEFT}
)


@dataclass(frozen=True)
class NormalisedName:
    """One observed name, everything that was done to it, and whether the result may be used.

    Both keys are carried. `collapsed` is the name with case, accents, punctuation and
    whitespace settled and its legal forms still on it; `key` is the same with the legal forms
    removed. Two records agreeing on `collapsed` agreed on their full names, and two agreeing
    only on `key` agreed after their legal forms were taken off, which is weaker evidence.
    Collapsing the two into one value would delete that distinction, and M14.3.2 is the leaf
    that needs it.

    `removed` holds the legal-form tokens that came off. Those are members of `SUFFIX_TOKENS`
    and never anything observed, so carrying them discloses nothing about the record: the
    reviewer learns that a name ended in "pte ltd", which they could have learnt from the
    vocabulary.
    """

    #: What the source said, verbatim. The evidence, unchanged.
    observed: str
    #: Case, accent, punctuation and whitespace settled. Legal forms still present.
    collapsed: str
    #: `collapsed` with trailing legal forms removed, unless removing them removed everything.
    key: str
    removed: tuple[str, ...]
    verdict: NameVerdict
    #: Which accent fold produced the two keys. A key stored beside an id that the running
    #: fold no longer has is detectably stale, where an unstamped key is silently stale.
    fold: str
    reason: str

    @property
    def is_usable(self) -> bool:
        return self.verdict is NameVerdict.USABLE

    @property
    def match_key(self) -> str | None:
        """The key the cascade may join on, or None for anything routed to review.

        The narrow surface is the guard. `key` is evidence and a reviewer may read it; this is
        the value a match is made on, and it is None rather than an empty string for every
        verdict that is not USABLE, so a caller that forgot to check the verdict joins on
        nothing instead of joining on "" and gathering every degenerate row in the estate.
        """
        return self.key if self.is_usable else None


def normalise_name(observed: str) -> NormalisedName:
    """Normalise one observed name and say whether the result may be matched on.

    Never raises. A name is data from a source system and every shape of it exists somewhere:
    blank fields, a single hyphen, a field holding only "Pte Ltd". Each of those gets a verdict
    and a sentence rather than an exception, because the caller is a backfill walking a million
    rows and an exception there is a backfill that stops on the worst row in the estate.

    The verdicts are checked most specific first. A name that is both entirely a suffix and
    shorter than the minimum, "Co" for instance, reports the suffix, because that is the
    question a reviewer can actually answer.
    """
    collapsed = collapse(observed)
    tokens = tuple(collapsed.split())
    kept, removed = strip_suffixes(tokens)
    key = " ".join(kept)

    if not key:
        verdict = NameVerdict.NOTHING_LEFT
        reason = (
            "nothing survived case folding, accent folding and punctuation stripping, so "
            "there is no name here to match on"
        )
    elif tokens and all(token in SUFFIX_TOKENS for token in tokens):
        verdict = NameVerdict.ENTIRELY_A_SUFFIX
        reason = (
            "every token is a legal form, so nothing was stripped; the empty key this would "
            "otherwise produce is equal to every other empty key"
        )
    elif len(key) < MIN_KEY_CHARS:
        verdict = NameVerdict.TOO_SHORT
        reason = (
            f"a key shorter than {MIN_KEY_CHARS} characters carries fewer than "
            f"{MIN_TRIGRAMS_FOR_A_MEASUREMENT} unpadded trigrams, so a similarity over it is "
            "not a measurement; a person decides this one"
        )
    else:
        verdict = NameVerdict.USABLE
        reason = "normalised to a key long enough to match on"

    return NormalisedName(
        observed=observed,
        collapsed=collapsed,
        key=key,
        removed=removed,
        verdict=verdict,
        fold=ACCENT_FOLD_ID,
        reason=reason,
    )


# ---------------------------------------------------------------------- Singapore UEN
class UenKind(enum.StrEnum):
    """Which of the three published UEN formats a value is in.

    Three, which is the whole documented set. There is no OTHER-as-fallback member: a value
    that matches none of the three is not a UEN of an undocumented kind, it is not a UEN, and a
    member meaning "probably fine" is how a mistyped registration number reaches stage one of
    the cascade and merges two companies on a hard identifier.
    """

    #: nnnnnnnnX. Businesses registered with ACRA. Nine characters.
    BUSINESS = "business"
    #: yyyynnnnnX. Local companies, the year of incorporation first. Ten characters.
    LOCAL_COMPANY = "local company"
    #: TyyPQnnnnX. Everything issued by another agency. Ten characters.
    OTHER = "other"


#: Business (ROB): eight digits and a check letter.
_UEN_BUSINESS_RE: Final = re.compile(r"^[0-9]{8}[A-Z]$")

#: Local company (ROC): a four-digit year of incorporation, five digits, a check letter.
_UEN_LOCAL_RE: Final = re.compile(r"^([0-9]{4})[0-9]{5}[A-Z]$")

#: Other agencies: a century letter, two year digits, a two-letter entity-type code, four
#: digits and a check letter.
#:
#: T, S and R are the published century prefixes, for the 2000s, the 1900s and the 1800s. The
#: two-letter code is checked for being two letters and is deliberately not checked against a
#: list of the codes in use: that list grows whenever an agency is added to the scheme, a stale
#: allowlist rejects the UEN of a body registered after the list was written, and a rejected
#: UEN is a real entity dropping out of stage one of the cascade in silence.
_UEN_OTHER_RE: Final = re.compile(r"^[TSR][0-9]{2}[A-Z]{2}[0-9]{4}[A-Z]$")

#: What a UEN is written with. Anything else, a hyphen or a space in the middle included, is a
#: value somebody reformatted, and accepting it would put two spellings of one registration
#: number into `canonical.identifier_hash` and produce two digests that never join.
_UEN_CHARSET_RE: Final = re.compile(r"^[0-9A-Z]+$")


@dataclass(frozen=True)
class UenCheck:
    """Whether a value is a UEN, in which format, and how much of that was actually checked.

    `check_character_verified` is False on every instance that can be built, and `__post_init__`
    refuses True. That is the mechanism rather than a default: a boolean with a permissive
    value available is a boolean somebody sets in a hurry, and the claim it would then be
    making is that this code verified something whose algorithm is not published. See
    `THE_CHECK_CHARACTER_IS_NOT_VALIDATED`.
    """

    valid: bool
    kind: UenKind | None
    #: The one spelling this UEN has: upper case, no surrounding whitespace. Empty when the
    #: value is not a UEN, so nothing invalid can be hashed by reaching for this field.
    canonical: str
    reason: str
    #: Structurally checked, always. Length, character classes at every position, and the
    #: century prefix where the format has one.
    format_verified: bool = True
    #: Never checked, and there is nowhere to say otherwise.
    check_character_verified: bool = False

    def __post_init__(self) -> None:
        if self.check_character_verified:
            msg = (
                "nothing in this repository verifies a UEN check character, because ACRA does "
                "not publish the algorithm; a UenCheck claiming otherwise would tell a caller "
                "that a hard identifier was validated when its last character was only "
                "checked for being a letter"
            )
            raise ValueError(msg)
        if self.valid and not self.canonical:
            msg = "a valid UEN has a canonical spelling; an empty one cannot be hashed or joined"
            raise ValueError(msg)
        if not self.valid and self.canonical:
            msg = (
                f"{self.canonical!r} is carried as the canonical form of a value that is not a "
                "UEN, which is a spelling something downstream will hash"
            )
            raise ValueError(msg)


def _invalid(reason: str) -> UenCheck:
    return UenCheck(valid=False, kind=None, canonical="", reason=reason)


def check_uen(value: str, *, year_ceiling: int | None = None) -> UenCheck:
    """Validate a Singapore UEN structurally, and say what was not validated (M14.2.6).

    Three formats, all published, all checked position by position: eight digits and a letter
    for a business, a four-digit year and five digits and a letter for a local company, and a
    century prefix and two year digits and a two-letter entity-type code and four digits and a
    letter for everything issued by another agency. The three are distinguished by length and
    by first character, so no value can match two of them and no ordering question arises.

    `year_ceiling` is optional and is the caller's clock, never this module's. Given, a local
    company whose incorporation year is in the future is refused, which catches a transposition
    like 2260 for 2026 that every character-class check passes. Not given, the year is checked
    for being four digits and no more, and there is deliberately no lower bound: the earliest
    year in the register is a fact about ACRA that nobody here has verified, and refusing on a
    guessed one would refuse the oldest companies in the estate.

    What is not validated is the check character. See `THE_CHECK_CHARACTER_IS_NOT_VALIDATED`.
    """
    candidate = value.strip().upper()
    if not candidate:
        return _invalid("a blank value is not a UEN")
    if not _UEN_CHARSET_RE.match(candidate):
        return _invalid(
            "a UEN is digits and capital letters only; a value with a separator in it is one "
            "somebody reformatted, and two spellings of one registration number hash to two "
            "digests that never join"
        )
    if _UEN_BUSINESS_RE.match(candidate):
        return UenCheck(
            valid=True,
            kind=UenKind.BUSINESS,
            canonical=candidate,
            reason="eight digits and a check letter: the ACRA business format",
        )
    local = _UEN_LOCAL_RE.match(candidate)
    if local:
        year = int(local.group(1))
        if year_ceiling is not None and year > year_ceiling:
            return _invalid(
                f"the incorporation year in this local-company UEN is later than "
                f"{year_ceiling}, so the value is mistyped rather than merely unfamiliar"
            )
        return UenCheck(
            valid=True,
            kind=UenKind.LOCAL_COMPANY,
            canonical=candidate,
            reason="a four-digit year, five digits and a check letter: the local-company format",
        )
    if _UEN_OTHER_RE.match(candidate):
        return UenCheck(
            valid=True,
            kind=UenKind.OTHER,
            canonical=candidate,
            reason=(
                "a century prefix, two year digits, a two-letter entity-type code, four "
                "digits and a check letter: the format used by the other issuing agencies"
            ),
        )
    return _invalid(
        f"{len(candidate)} characters in a shape matching none of the three published UEN "
        "formats; treating it as one would put a mistyped registration number into the stage "
        "that merges on a hard identifier alone"
    )
