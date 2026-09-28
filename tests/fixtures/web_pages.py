"""Web pages as a link answers with them, recorded as bytes so no test reaches the internet.

Each shape is the kind of page an administrator pastes a link to, built by hand from the markup
the commonest page structures use (HTML5's `header`, `nav`, `main`, `article`, `aside` and `footer`
landmarks, a cookie banner, inline scripts and styles, a pricing table), about a fictional
company on the reserved `example.org` domain. None is copied from a real site. The one shape that
matters most is `SCRIPTED_SHELL`: a single-page application's first answer, which carries a mount
point and a script and none of the page's words.

Task ids: none
"""

from __future__ import annotations

from typing import Final

#: Where the fictional company's pages live. `example.org` is reserved for documentation.
SITE: Final = "https://www.example.org"

#: The address the pricing page is added by, with a tracking query a share link would carry.
PRICING_URL: Final = f"{SITE}/services/pricing?utm_source=newsletter&token=abc123#plans"

#: What the pricing page's words include, and a word that appears only in its furniture.
PRICING_WORD: Final = "TEALPLAN"
FURNITURE_WORD: Final = "NAVONLY"
SCRIPT_WORD: Final = "SCRIPTONLY"

#: A server-rendered page with every landmark, a script, a style and a banner outside `main`.
PRICING_PAGE: Final = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Care plans &amp; pricing | Example Services</title>
  <style>.plan {{ color: teal; }} /* {SCRIPT_WORD} */</style>
  <script>window.dataLayer = ["{SCRIPT_WORD}"];</script>
</head>
<body>
  <div class="cookie-banner">We use cookies. <button>Accept {FURNITURE_WORD}</button></div>
  <header><a href="/">Example Services</a>
    <nav><ul><li><a href="/about">About {FURNITURE_WORD}</a></li><li>Contact</li></ul></nav>
  </header>
  <main>
    <article>
      <h1>Care plans</h1>
      <p>Every <strong>{PRICING_WORD}</strong> care plan includes
         two site visits a year and a named engineer.</p>
      <h2>What each plan costs</h2>
      <table>
        <thead><tr><th>Plan</th><th>Visits</th><th>Monthly</th></tr></thead>
        <tbody>
          <tr><td>Essential</td><td>2</td><td>120.00</td></tr>
          <tr><td>Priority | plus</td><td>4</td><td>240.00</td></tr>
        </tbody>
      </table>
      <h2>Booking</h2>
      <ul><li><p>Call the desk</p></li><li>Or write to us</li></ul>
      <p>Lines are open<br>Monday to Friday.</p>
      <svg aria-hidden="true"><title>icon</title><path d="M0 0"/></svg>
    </article>
    <aside>Related: {FURNITURE_WORD} offers</aside>
  </main>
  <footer>Copyright Example Services {FURNITURE_WORD}</footer>
  <script src="/app.js"></script>
</body>
</html>
""".encode()

#: A page that marks no content region: everything outside the skipped furniture is read.
PLAIN_PAGE: Final = b"""<html><head><title>Opening hours</title></head>
<body><nav>Home NAVONLY</nav>
<h2>Opening hours</h2><p>The TEALHOURS desk opens at nine.</p>
<footer>NAVONLY footer</footer></body></html>
"""

#: A single-page application's first answer: a mount point, a script, and no words at all.
SCRIPTED_SHELL: Final = b"""<!doctype html><html><head><title>Portal</title>
<script type="module" src="/assets/index.js"></script></head>
<body><noscript>You need to enable JavaScript to run this app.</noscript>
<div id="root"></div></body></html>
"""

#: A page in Latin-1 rather than UTF-8: an e with an acute accent is one byte, 0xE9.
LATIN1_PAGE: Final = (
    b"<html><head><meta charset='iso-8859-1'><title>Caf\xe9</title></head>"
    b"<body><p>Caf\xe9 opening hours.</p></body></html>"
)

#: A text answer that is not a page: Markdown, as a raw file host serves it.
MARKDOWN_ANSWER: Final = b"# Handover notes\n\nSign the TEALNOTE list before leaving.\n"

#: A PNG's first bytes, which a link to an image answers with.
PNG_ANSWER: Final = bytes((0x89,)) + b"PNG" + bytes((0x0D, 0x0A, 0x1A, 0x0A)) + bytes(32)
