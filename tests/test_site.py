"""
The public website (docs/, built from site/ and served by GitHub Pages) and the README. They are the first thing a stranger sees,
so what makes the site findable and trustworthy is pinned down here, for every page: search-engine essentials, working links,
no third-party requests, structured data that says what the page says, a sitemap that matches the pages, honest wording about
risk, and no personal name.
"""

import importlib.util
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE_URL = "https://sideeffects69.github.io/Magic-Apply-Jobs/"
ALLOWED_OUTSIDE = ("https://github.com/sideeffects69/Magic-Apply-Jobs", "https://www.linkedin.com/help/linkedin/answer/")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "site" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(ROOT / "site"))
PAGES_MODULE = _load("magic_site_pages", "pages.py")
BUILD = _load("magic_site_build", "build.py")
PAGES = PAGES_MODULE.PAGES


def _squash(text: str) -> str:
    return " ".join(text.split())


class _Page(HTMLParser):
    '''Collects what the tests need from one HTML page.'''

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta = {}                  # name/property -> content
        self.tags = []                  # (tag, attrs dict)
        self.jsonld = []
        self.ids = set()
        self.h1_count = 0
        self.faq = []                   # (question, answer) from the visible <details class="faq"> blocks
        self.main_text = []
        self._capture = None            # what the next text belongs to
        self._buffer = []
        self._details = None
        self._in_main = False
        self._skip = 0
        self.sitelist_links = []        # links inside the HTML site map's own list (not the header or footer)
        self._in_sitelist = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "main":
            self._in_main = True
        if tag == "ul" and "sitelist" in (attrs.get("class") or "").split():
            self._in_sitelist = True
        if tag == "a" and self._in_sitelist:
            self.sitelist_links.append(attrs.get("href"))
        if tag == "meta":
            key = attrs.get("name") or attrs.get("property")
            if key:
                self.meta[key] = attrs.get("content", "")
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "title":
            self._start("title")
        elif tag == "script":
            self._skip += 1
            if attrs.get("type") == "application/ld+json":
                self._start("jsonld")
        elif tag == "details" and "faq" in (attrs.get("class") or "").split():
            self._details = {"q": "", "a": ""}
        elif tag == "summary" and self._details is not None:
            self._start("question")
        elif tag == "p" and self._details is not None:
            self._start("answer")

    def handle_endtag(self, tag):
        if tag == "main":
            self._in_main = False
        if tag == "ul":
            self._in_sitelist = False
        if tag == "title" and self._capture == "title":
            self.title = _squash(self._finish())
        elif tag == "script":
            self._skip -= 1
            if self._capture == "jsonld":
                self.jsonld.append(self._finish())
        elif tag == "summary" and self._capture == "question":
            self._details["q"] = _squash(self._finish())
        elif tag == "p" and self._capture == "answer":
            self._details["a"] = _squash(self._finish())
        elif tag == "details" and self._details is not None:
            self.faq.append((self._details["q"], self._details["a"]))
            self._details = None

    def handle_data(self, data):
        if self._capture:
            self._buffer.append(data)
        if self._in_main and not self._skip:
            self.main_text.append(data)

    def _start(self, what):
        self._capture, self._buffer = what, []

    def _finish(self):
        text, self._capture, self._buffer = "".join(self._buffer), None, []
        return text

    @property
    def words(self) -> int:
        return len(re.findall(r"[A-Za-z0-9'’-]+", " ".join(self.main_text)))


def _file(page: dict) -> Path:
    return DOCS / page["slug"] / "index.html" if page["slug"] else DOCS / "index.html"


_CACHE: dict = {}


def _parse(path: Path) -> _Page:
    if path not in _CACHE:
        page = _Page()
        page.feed(path.read_text(encoding="utf-8"))
        _CACHE[path] = page
    return _CACHE[path]


def parsed(page: dict) -> _Page:
    return _parse(_file(page))


everypage = pytest.mark.parametrize("page", PAGES, ids=[p["slug"] or "home" for p in PAGES])
GUIDES = [p for p in PAGES if p["kind"] == "guide"]


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:32]
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", header[16:24])


def _local_target(value: str, base: Path) -> Path | None:
    '''The file a relative link points at, or None for links that leave the site or stay on the page.'''
    if re.match(r"^(https?:|mailto:|#|data:)", value):
        return None
    target = (base / value.split("#")[0].split("?")[0]).resolve()
    return target / "index.html" if target.is_dir() else target


# ---------------------------------------------------------------------------
# The sources and the folder that GitHub Pages serves must agree
# ---------------------------------------------------------------------------
def test_docs_is_exactly_what_the_sources_produce():
    stale = [str(path.relative_to(ROOT)) for path, text in BUILD.build().items() if not path.exists() or path.read_text(encoding="utf-8") != text]
    assert not stale, "run `python site/build.py` (and never edit these by hand): " + ", ".join(stale)


# ---------------------------------------------------------------------------
# What search engines and link previews read, on every page
# ---------------------------------------------------------------------------
@everypage
def test_the_title_and_description_fit_what_search_results_show(page):
    doc = parsed(page)
    assert 20 <= len(doc.title) <= 60, f"title is {len(doc.title)} characters: {doc.title!r}"
    description = doc.meta["description"]
    assert 120 <= len(description) <= 160, f"description is {len(description)} characters"
    assert doc.title == page["title"] and description == page["description"]


def test_every_title_and_description_is_different():
    titles = [parsed(p).title for p in PAGES]
    descriptions = [parsed(p).meta["description"] for p in PAGES]
    assert len(set(titles)) == len(titles) and len(set(descriptions)) == len(descriptions), "duplicate titles or descriptions compete with each other"


def test_the_pages_target_the_words_people_search_for():
    home = parsed(PAGES[0])
    for phrase in ("free", "open-source", "LinkedIn"):
        assert phrase.lower() in (home.title + " " + home.meta["description"]).lower()
    wanted = {"how-to-auto-apply-on-linkedin": "auto apply", "linkedin-easy-apply-limit": "easy apply limit", "is-linkedin-auto-apply-safe": "safe",
              "apply-on-company-websites": "company", "free-linkedin-auto-apply-tools": "free"}
    for slug, phrase in wanted.items():
        assert phrase in parsed(PAGES_MODULE.BY_SLUG[slug]).title.lower(), f"{slug}: the title should contain {phrase!r}"


@everypage
def test_every_page_has_one_h1_a_language_and_the_right_canonical_address(page):
    doc = parsed(page)
    assert doc.h1_count == 1
    assert next(attrs for tag, attrs in doc.tags if tag == "html").get("lang") == "en"
    canonical = [attrs["href"] for tag, attrs in doc.tags if tag == "link" and attrs.get("rel") == "canonical"]
    assert canonical == [PAGES_MODULE.url(page["slug"])]
    assert "noindex" not in doc.meta.get("robots", "")


@everypage
def test_link_previews_have_a_real_image_at_the_size_they_announce(page):
    doc = parsed(page)
    image = doc.meta["og:image"]
    assert image.startswith(SITE_URL) and image == doc.meta["twitter:image"]
    assert _png_size(DOCS / image.removeprefix(SITE_URL)) == (int(doc.meta["og:image:width"]), int(doc.meta["og:image:height"])) == (1200, 630)
    assert doc.meta["twitter:card"] == "summary_large_image"
    assert doc.meta["og:url"] == PAGES_MODULE.url(page["slug"]) and doc.meta["og:image:alt"]


def test_the_sitemap_lists_every_page_with_its_date_and_nothing_else():
    root = ET.parse(DOCS / "sitemap.xml").getroot()
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    listed = {u.find(ns + "loc").text: u.find(ns + "lastmod").text for u in root.findall(ns + "url")}
    assert listed == {PAGES_MODULE.url(p["slug"]): p["updated"] for p in PAGES}
    for address in listed:
        assert _file({"slug": address.removeprefix(SITE_URL).strip("/")}).exists(), address


def test_the_html_site_map_links_to_every_other_page():
    sitemap = next(p for p in PAGES if p["slug"] == "sitemap")
    hrefs = set(parsed(sitemap).sitelist_links)
    for page in PAGES:
        if page["slug"] != "sitemap":
            assert ("../" + page["slug"] + "/" if page["slug"] else "../") in hrefs, page["slug"] or "home"
    assert "../sitemap.xml" in {attrs["href"] for tag, attrs in parsed(sitemap).tags if tag == "a" and "href" in attrs}


def test_the_not_found_page_is_kept_out_of_search_results():
    assert _parse(DOCS / "404.html").meta["robots"] == "noindex"


def test_github_pages_serves_the_folder_as_is():
    assert (DOCS / ".nojekyll").exists()


def test_the_google_search_console_verification_file_is_kept_exactly_as_google_gave_it():
    # Search Console re-checks this file now and then. Deleting it, or changing a single character, un-verifies the site.
    files = sorted(DOCS.glob("google*.html"))
    assert files, "docs/google<code>.html is what proves to Google that the site is yours - do not delete it"
    for path in files:
        assert path.read_text(encoding="utf-8").strip() == f"google-site-verification: {path.name}", path.name


# ---------------------------------------------------------------------------
# Structured data must say what the page says
# ---------------------------------------------------------------------------
def _blocks(doc):
    return {block["@type"]: block for block in map(json.loads, doc.jsonld)}


def test_the_home_page_describes_a_free_open_source_application():
    blocks = _blocks(parsed(PAGES[0]))
    app = blocks["SoftwareApplication"]
    assert app["name"] == "Magic Apply - Jobs" and app["url"] == SITE_URL and app["softwareVersion"] == PAGES_MODULE.VERSION
    assert app["offers"]["price"] == "0" and app["isAccessibleForFree"] is True and "mit" in app["license"].lower()
    assert "aggregateRating" not in app and "review" not in app, "never publish ratings nobody gave"
    for screenshot in app["screenshot"]:
        assert (DOCS / screenshot.removeprefix(SITE_URL)).exists(), screenshot


@everypage
def test_the_faq_data_matches_the_faq_on_the_page(page):
    doc = parsed(page)
    if not page["faq"]:
        assert not doc.faq and "FAQPage" not in _blocks(doc)
        return
    questions = _blocks(doc)["FAQPage"]["mainEntity"]
    from_json = [(_squash(q["name"]), _squash(q["acceptedAnswer"]["text"])) for q in questions]
    assert from_json == doc.faq and len(doc.faq) == len(page["faq"]), "search engines may only show answers that are visible on the page"


@pytest.mark.parametrize("page", [p for p in PAGES if p["slug"]], ids=lambda p: p["slug"])
def test_inner_pages_have_breadcrumbs_in_the_page_and_in_the_data(page):
    doc = parsed(page)
    crumbs = _blocks(doc)["BreadcrumbList"]["itemListElement"]
    assert [c["name"] for c in crumbs] == ["Home", page["crumb"]] and crumbs[1]["item"] == PAGES_MODULE.url(page["slug"])
    assert any(tag == "nav" and attrs.get("aria-label") == "Breadcrumb" for tag, attrs in doc.tags)


@pytest.mark.parametrize("page", GUIDES, ids=lambda p: p["slug"])
def test_guides_carry_article_data_with_dates_and_no_personal_author(page):
    article = _blocks(parsed(page))["Article"]
    assert article["dateModified"] == page["updated"] and article["headline"] == page["h1"] and len(article["headline"]) <= 110
    assert article["author"]["@type"] == "Organization", "the site does not name a person"


# ---------------------------------------------------------------------------
# Content that earns its place
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("page", GUIDES, ids=lambda p: p["slug"])
def test_every_guide_has_real_substance_and_links_onward(page):
    doc = parsed(page)
    assert doc.words >= 600, f"{page['slug']} has only {doc.words} words: thin pages do not help anyone"
    inner = {attrs["href"] for tag, attrs in doc.tags if tag == "a" and re.match(r"^\.\./[a-z-]+/$", attrs.get("href", ""))}
    assert len(inner) >= 4, f"{page['slug']} links to only {len(inner)} other pages"


def test_every_page_can_be_reached_from_the_home_page():
    home_links = {attrs["href"] for tag, attrs in parsed(PAGES[0]).tags if tag == "a" and "href" in attrs}
    for page in PAGES[1:]:
        assert page["slug"] + "/" in home_links, f"the home page does not link to {page['slug']}"


@pytest.mark.parametrize("page", GUIDES, ids=lambda p: p["slug"])
def test_every_guide_has_a_table_of_contents_that_works(page):
    doc = parsed(page)
    anchors = [attrs["href"][1:] for tag, attrs in doc.tags if tag == "a" and attrs.get("href", "").startswith("#") and attrs["href"] != "#main"]
    assert len(anchors) >= 3 and all(a in doc.ids for a in anchors)


# ---------------------------------------------------------------------------
# Honest about risk and about what is only reported
# ---------------------------------------------------------------------------
def test_the_safety_guide_says_plainly_that_the_risk_is_real_and_cites_linkedin():
    doc = parsed(PAGES_MODULE.BY_SLUG["is-linkedin-auto-apply-safe"])
    text = _squash(" ".join(doc.main_text)).lower()
    assert "not risk-free" in text and "restricted or shut down" in text and "nothing on this page can make it zero" in text
    assert "undetectable" in text and "do not claim" in text, "it must say the safety settings do not make the tool undetectable"
    hrefs = {attrs.get("href") for tag, attrs in doc.tags if tag == "a"}
    assert PAGES_MODULE.LINKEDIN_PROHIBITED in hrefs, "cite LinkedIn's own rule instead of paraphrasing it"


def test_the_easy_apply_limit_guide_presents_the_number_as_a_report_not_a_fact():
    text = _squash(" ".join(parsed(PAGES_MODULE.BY_SLUG["linkedin-easy-apply-limit"]).main_text)).lower()
    assert "has not published an official number" in text and "report, not a rule" in text and "believe linkedin" in text


def test_the_pages_admit_the_tool_is_a_beta_tested_on_mock_sites():
    for slug in ("", "apply-on-company-websites", "how-to-auto-apply-on-linkedin"):
        text = _squash(" ".join(parsed(PAGES_MODULE.BY_SLUG[slug]).main_text)).lower()
        assert "beta" in text, slug or "home"
    home = _squash((DOCS / "index.html").read_text(encoding="utf-8")).lower()
    assert "mock" in home and "not affiliated with" in home and "own risk" in home
    assert "not verified" in _squash(" ".join(parsed(PAGES_MODULE.BY_SLUG["faq"]).main_text)).lower() or "have not verified" in _squash(
        " ".join(parsed(PAGES_MODULE.BY_SLUG["faq"]).main_text)).lower(), "no claims about named applicant tracking systems"


# ---------------------------------------------------------------------------
# Images, links, and no third parties
# ---------------------------------------------------------------------------
@everypage
def test_every_image_has_alt_text_and_the_size_of_its_file(page):
    for tag, attrs in parsed(page).tags:
        if tag != "img":
            continue
        target = _local_target(attrs["src"], _file(page).parent)
        assert target and target.exists(), attrs["src"]
        if target.suffix == ".png":
            assert (int(attrs["width"]), int(attrs["height"])) == _png_size(target), f"{attrs['src']}: width/height must match the file"
            assert len(attrs.get("alt", "")) >= 20, f"{attrs['src']} needs a real description"


@everypage
def test_every_local_link_and_in_page_anchor_works(page):
    doc = parsed(page)
    for tag, attrs in doc.tags:
        for name in ("href", "src"):
            value = attrs.get(name)
            if not value:
                continue
            if value.startswith("#"):
                assert value[1:] in doc.ids, f"{value} points at nothing"
            else:
                target = _local_target(value, _file(page).parent)
                assert target is None or target.exists(), f"{tag} {name}={value!r} does not exist"


@everypage
def test_the_site_loads_nothing_from_anywhere_else(page):
    for tag, attrs in parsed(page).tags:
        if tag == "script":
            assert attrs.get("type") == "application/ld+json", "no scripts: the site promises no tracking"
        if tag == "link" and attrs.get("rel") in ("preload", "preconnect", "dns-prefetch"):
            pytest.fail(f"a link to {attrs.get('href')} would load from outside the site")
        if tag == "link" and attrs.get("rel") == "stylesheet":
            assert not re.match(r"^(https?:)?//", attrs["href"]), "stylesheets must be the site's own"
        if tag in ("img", "iframe", "video", "audio", "source"):
            assert not re.match(r"^(https?:)?//", attrs.get("src", "")), attrs


@everypage
def test_outside_links_go_only_to_the_project_or_linkedins_own_help_pages(page):
    for tag, attrs in parsed(page).tags:
        href = attrs.get("href", "")
        if tag == "a" and re.match(r"^https?://", href):
            assert href.startswith(ALLOWED_OUTSIDE), href
            if "linkedin.com" in href:
                assert "noopener" in attrs.get("rel", ""), "outside links open safely"


# ---------------------------------------------------------------------------
# Keeping a personal name out
# ---------------------------------------------------------------------------
def test_the_maintainers_name_is_not_on_the_site_or_in_the_readme():
    paths = [*DOCS.rglob("*.html"), *DOCS.rglob("*.xml"), *(ROOT / "site").rglob("*.html"), ROOT / "site" / "pages.py", ROOT / "README.md",
             ROOT / "CONTRIBUTING.md"]
    for path in paths:
        assert "abhyankar" not in path.read_text(encoding="utf-8").lower(), f"{path.name} names the maintainer"


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------
def _slug(heading: str) -> str:
    '''GitHub's anchor for a heading.'''
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", heading.strip().lower()))


def test_every_readme_link_and_image_points_at_something_real():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    anchors = {_slug(match.group(1)) for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", readme, re.MULTILINE)}
    targets = re.findall(r"\]\(([^)\s]+)\)", readme) + re.findall(r'(?:src|href)="([^"]+)"', readme)
    assert len(targets) > 15
    for target in targets:
        if target.startswith("#"):
            assert target[1:] in anchors, f"README link {target} matches no heading"
        else:
            local = _local_target(target, ROOT)
            assert local is None or local.exists(), f"README points at {target}, which is not in the repository"


def test_the_readme_links_to_the_website_and_the_downloads():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert SITE_URL in readme and "https://github.com/sideeffects69/Magic-Apply-Jobs/releases" in readme
    assert "releases/latest" not in readme, "every release is a pre-release, so 'latest' does not list them"
