"""
Builds the website in docs/ from site/pages.py, site/template.html and site/content/*.html.

    python site/build.py           write docs/
    python site/build.py --check   exit 1 if docs/ is not what the sources produce (a test runs this too)

The header, footer, breadcrumbs, structured data, FAQ blocks, sitemap.xml and the HTML site map all come from one place,
so a change to a page's title or a question is made once and cannot drift between the page, the data and the sitemap.
"""

import html
import json
import pathlib
import re
import string
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pages as P  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DOCS = ROOT / "docs"

NAV = ["how-to-auto-apply-on-linkedin", "linkedin-easy-apply-limit", "is-linkedin-auto-apply-safe", "apply-on-company-websites", "faq"]
FOOTER_GUIDES = ["how-to-auto-apply-on-linkedin", "linkedin-easy-apply-limit", "is-linkedin-auto-apply-safe", "apply-on-company-websites",
                 "free-linkedin-auto-apply-tools", "faq"]
OG_ALT = "Magic Apply - Jobs: free, open-source job application assistant, shown next to its control panel."


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def base(page: dict) -> str:
    return "" if page["slug"] == "" else "../"


def link(page: dict, slug: str) -> str:
    '''Relative link from `page` to the page `slug`.'''
    return base(page) + (slug + "/" if slug else "")


def nice_date(iso: str) -> str:
    day = date.fromisoformat(iso)
    return f"{day.day} {day.strftime('%B %Y')}"


def canonical(page: dict) -> str:
    return P.url(page["slug"])


# ---------------------------------------------------------------------------
# Pieces
# ---------------------------------------------------------------------------
def header(page: dict) -> str:
    links = "\n".join(f'      <a class="hide-sm" href="{link(page, slug)}">{esc(P.BY_SLUG[slug]["nav"])}</a>' for slug in NAV)
    return f'''<header class="site">
  <div class="wrap">
    <a class="brand" href="{base(page) or "./"}" aria-label="{esc(P.SITE_NAME)}, home">
      <img src="{base(page)}favicon.svg" width="30" height="30" alt="">
      <span>{esc(P.SITE_NAME)}</span> <span class="pill">Beta</span>
    </a>
    <nav class="main" aria-label="Main">
{links}
      <a class="btn btn-primary btn-sm" href="{P.RELEASES_URL}">Download</a>
    </nav>
  </div>
</header>'''


def footer(page: dict) -> str:
    guides = "\n".join(f'        <li><a href="{link(page, slug)}">{esc(P.BY_SLUG[slug]["nav"] if slug != "faq" else "FAQ")}</a></li>' for slug in FOOTER_GUIDES)
    return f'''<footer>
  <div class="wrap">
    <div class="cols">
      <div>
        <p><strong>{esc(P.SITE_NAME)}</strong></p>
        <p>Free and open source under the MIT License.</p>
      </div>
      <div>
        <p><strong>Guides</strong></p>
        <ul aria-label="Guides">
{guides}
        </ul>
      </div>
      <div>
        <p><strong>Project</strong></p>
        <ul aria-label="Project links">
          <li><a href="{P.REPO_URL}">Source on GitHub</a></li>
          <li><a href="{P.RELEASES_URL}">Releases</a></li>
          <li><a href="{P.REPO_URL}/issues">Report an issue</a></li>
          <li><a href="{P.REPO_URL}/blob/main/CONTRIBUTING.md">Contribute</a></li>
          <li><a href="{P.REPO_URL}/blob/main/LICENSE">License</a></li>
          <li><a href="{link(page, "sitemap")}">Site map</a></li>
        </ul>
      </div>
    </div>
    <p class="legal">{esc(P.SITE_NAME)} is an independent open-source project. It is not affiliated with, endorsed by or sponsored by LinkedIn or Google; those names belong to their owners. The tool acts through your own accounts and is provided as is, without warranty. You are responsible for following the terms of every website you use it with. Screenshots on this site use made-up example data.</p>
  </div>
</footer>'''


def breadcrumb(page: dict) -> str:
    return (f'<nav class="crumbs" aria-label="Breadcrumb"><a href="{base(page) or "./"}">Home</a> <span aria-hidden="true">&rsaquo;</span> '
            f'<span aria-current="page">{esc(page["crumb"])}</span></nav>')


def faq_block(page: dict, ids: list[str], heading_level: int = 2, more: bool = False) -> str:
    items = "\n".join(
        f'    <details class="faq">\n      <summary>{esc(P.FAQ[i][0])}</summary>\n      <p>{esc(P.FAQ[i][1])}</p>\n    </details>' for i in ids)
    extra = f'\n    <p class="fine" style="margin-top:18px">More answers on the <a href="{link(page, "faq")}">full FAQ page</a>.</p>' if more else ""
    return f'<section class="faq-block" id="faq">\n  <h{heading_level}>Frequently asked questions</h{heading_level}>\n{items}{extra}\n</section>'


def related_block(page: dict) -> str:
    if not page.get("related"):
        return ""
    cards = "\n".join(
        f'    <a href="{link(page, slug)}">{esc(P.BY_SLUG[slug]["crumb"])}<span>{esc(P.BY_SLUG[slug]["description"])}</span></a>' for slug in page["related"])
    return f'<section class="related-block" id="related">\n  <h2>Related guides</h2>\n  <div class="related">\n{cards}\n  </div>\n</section>'


def guides_block(page: dict) -> str:
    cards = "\n".join(
        f'      <a class="card guide" href="{link(page, slug)}"><h3>{esc(P.BY_SLUG[slug]["crumb"])}</h3><p>{esc(P.BY_SLUG[slug]["description"])}</p></a>'
        for slug in FOOTER_GUIDES)
    return f'''<section id="guides" class="alt">
  <div class="wrap">
    <div class="section-head">
      <h2>Guides: what to know before you auto apply</h2>
      <p>The questions people search for most, answered plainly, including the risks.</p>
    </div>
    <div class="cards three">
{cards}
    </div>
  </div>
</section>'''


def toc(fragment: str) -> str:
    entries = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', fragment)
    if len(entries) < 3:
        return ""
    items = "\n".join(f'    <li><a href="#{anchor}">{title}</a></li>' for anchor, title in entries)
    return f'<nav class="toc" aria-label="On this page">\n  <strong>On this page</strong>\n  <ol>\n{items}\n  </ol>\n</nav>'


def sitemap_body(page: dict) -> str:
    rows = []
    for other in P.PAGES:
        if other["slug"] == "sitemap":
            continue
        rows.append(f'    <li><a href="{link(page, other["slug"])}">{esc(other["crumb"] if other["slug"] else "Home: Magic Apply - Jobs")}</a>'
                    f'<span>{esc(other["description"])}</span></li>')
    tool = [("Download the tool (Releases)", P.RELEASES_URL, "The portable Windows .exe, with its SHA-256 in the release notes."),
            ("Source code on GitHub", P.REPO_URL, "Read every line, report issues and contribute."),
            ("License (MIT)", P.REPO_URL + "/blob/main/LICENSE", "Free and open source.")]
    outside = "\n".join(f'    <li><a href="{u}">{esc(t)}</a><span>{esc(d)}</span></li>' for t, u, d in tool)
    return (f'<h2 id="pages">Pages on this site</h2>\n<ul class="sitelist">\n' + "\n".join(rows) + '\n</ul>\n'
            f'<h2 id="tool">The tool itself</h2>\n<ul class="sitelist">\n{outside}\n</ul>\n'
            f'<p class="fine">Machine-readable version: <a href="{base(page)}sitemap.xml">sitemap.xml</a>.</p>')


TOKENS = {"VERSION": P.VERSION, "RELEASES": P.RELEASES_URL, "REPO": P.REPO_URL, "SITE": P.SITE_URL,
          "LI_PROHIBITED": P.LINKEDIN_PROHIBITED, "LI_AUTOMATED": P.LINKEDIN_AUTOMATED, "LI_RESTRICTED": P.LINKEDIN_RESTRICTED}


def fill(fragment: str, page: dict) -> str:
    '''Replaces {{tokens}} in a content fragment: links between pages, the asset base, and the shared blocks.'''
    fragment = re.sub(r"\{\{link:([a-z0-9-]*)\}\}", lambda m: link(page, m.group(1)), fragment)
    fragment = fragment.replace("{{base}}", base(page))
    for name, value in TOKENS.items():
        fragment = fragment.replace("{{" + name + "}}", value)
    if "{{GUIDES}}" in fragment:
        fragment = fragment.replace("{{GUIDES}}", guides_block(page))
    if "{{FAQ}}" in fragment:
        wrapper = faq_block(page, page["faq"], 2, page.get("faq_more", False))
        if page["kind"] == "home":
            wrapper = f'<section id="faq">\n  <div class="wrap" style="max-width:820px">\n{wrapper}\n  </div>\n</section>'
        fragment = fragment.replace("{{FAQ}}", wrapper)
    leftover = re.findall(r"\{\{[^}]*\}\}", fragment)
    assert not leftover, f"unfilled tokens on {page['slug'] or 'home'}: {leftover}"
    return fragment


# ---------------------------------------------------------------------------
# Structured data
# ---------------------------------------------------------------------------
def ld(data: dict) -> str:
    text = json.dumps(data, indent=2, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{text}\n</script>'


def faq_ld(ids: list[str]) -> dict:
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": P.FAQ[i][0], "acceptedAnswer": {"@type": "Answer", "text": P.FAQ[i][1]}} for i in ids]}


def breadcrumb_ld(page: dict) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": P.SITE_URL},
        {"@type": "ListItem", "position": 2, "name": page["crumb"], "item": canonical(page)}]}


def software_ld() -> dict:
    return {
        "@context": "https://schema.org", "@type": "SoftwareApplication", "name": P.SITE_NAME, "url": P.SITE_URL,
        "description": "Free, open-source tool that finds jobs on LinkedIn, applies with Easy Apply and fills in company career-site application forms. "
                       "It runs on your own computer and keeps no data after you close it.",
        "applicationCategory": "BusinessApplication", "operatingSystem": "Windows, macOS, Linux", "softwareVersion": P.VERSION,
        "softwareRequirements": "Google Chrome", "isAccessibleForFree": True, "license": "https://opensource.org/license/mit",
        "downloadUrl": P.RELEASES_URL, "image": P.OG_IMAGE,
        "screenshot": [P.SITE_URL + f"assets/screenshot-{name}.png" for name in ("run", "search", "applied-jobs", "failed-jobs")],
        "featureList": [
            "Applies with LinkedIn Easy Apply",
            "Follows other jobs to the company's own application site and fills in the form",
            "Signs in with Google when a site asks, without ever typing your Google password",
            "Never submits with a required question empty and never invents an answer",
            "Optional AI answers (OpenAI, Gemini or DeepSeek)",
            "Erases your data when you close it, with backup and restore",
            "Failed-jobs list with reasons, links and screenshots"],
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
    }


def article_ld(page: dict) -> dict:
    org = {"@type": "Organization", "name": P.SITE_NAME, "url": P.SITE_URL}
    return {"@context": "https://schema.org", "@type": "Article", "headline": page["h1"], "description": page["description"],
            "image": P.OG_IMAGE, "datePublished": P.PUBLISHED, "dateModified": page["updated"],
            "mainEntityOfPage": {"@type": "WebPage", "@id": canonical(page)}, "author": org,
            "publisher": {**org, "logo": {"@type": "ImageObject", "url": P.SITE_URL + "apple-touch-icon.png"}}}


def structured_data(page: dict) -> str:
    blocks = []
    if page["kind"] == "home":
        blocks += [software_ld(), {"@context": "https://schema.org", "@type": "WebSite", "name": P.SITE_NAME, "url": P.SITE_URL}]
    elif page["kind"] == "guide":
        blocks += [article_ld(page), breadcrumb_ld(page)]
    else:
        blocks += [breadcrumb_ld(page)]
    if page["faq"]:
        blocks.append(faq_ld(page["faq"]))
    return "\n".join(ld(block) for block in blocks)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def render(page: dict) -> str:
    template = string.Template((SITE / "template.html").read_text(encoding="utf-8"))
    kind = page["kind"]
    if kind == "home":
        body = fill((SITE / "content" / "home.html").read_text(encoding="utf-8"), page).rstrip()
    else:
        fragment = sitemap_body(page) if kind == "sitemap" else fill((SITE / "content" / f"{page['content']}.html").read_text(encoding="utf-8"), page)
        faq = faq_block(page, page["faq"], 2) if page["faq"] and "{{FAQ}}" not in fragment and kind != "faq" else ""
        if kind == "faq":
            faq = faq_block(page, page["faq"], 2).replace('<section class="faq-block" id="faq">\n  <h2>Frequently asked questions</h2>\n', '<section class="faq-block" id="faq">\n')
        body = f'''<div class="wrap narrow">
  {breadcrumb(page)}
  <article class="article">
    <header>
      <h1>{esc(page["h1"])}</h1>
      <p class="lede">{esc(page["lede"])}</p>
      <p class="meta">Updated <time datetime="{page["updated"]}">{nice_date(page["updated"])}</time></p>
    </header>
    {toc(fragment) if kind == "guide" else ""}
    {fragment.rstrip()}
    {faq}
    {related_block(page)}
  </article>
</div>'''
    og_type = "article" if kind == "guide" else "website"
    return template.substitute(
        title=esc(page["title"]), description=esc(page["description"]), canonical=canonical(page), base=base(page), og_type=og_type,
        og_image=P.OG_IMAGE, og_alt=esc(OG_ALT), site_name=esc(P.SITE_NAME), jsonld=structured_data(page),
        header=header(page), body=body, footer=footer(page))


def sitemap_xml() -> str:
    urls = "\n".join(f"  <url>\n    <loc>{P.url(page['slug'])}</loc>\n    <lastmod>{page['updated']}</lastmod>\n  </url>" for page in P.PAGES)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n'


def build() -> dict[pathlib.Path, str]:
    '''Everything the sources produce, as {path: text}. Nothing is written here.'''
    out = {}
    for page in P.PAGES:
        target = DOCS / page["slug"] / "index.html" if page["slug"] else DOCS / "index.html"
        out[target] = render(page)
    out[DOCS / "sitemap.xml"] = sitemap_xml()
    return out


def main(argv: list[str]) -> int:
    built = build()
    if "--check" in argv:
        stale = [str(path.relative_to(ROOT)) for path, text in built.items() if not path.exists() or path.read_text(encoding="utf-8") != text]
        if stale:
            print("docs/ is out of date with site/ - run `python site/build.py`:", *stale, sep="\n  ")
            return 1
        print(f"docs/ is up to date ({len(built)} files)")
        return 0
    for path, text in built.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print("wrote", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
