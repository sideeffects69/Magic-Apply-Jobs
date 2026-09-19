"""
The public website (docs/, served by GitHub Pages) and the README. They are the first thing a stranger sees, so the basics
that make the site findable and trustworthy are pinned down here: search-engine essentials, working links, no third-party
requests, structured data that says what the page says, and no personal name.
"""

import json
import re
import struct
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE_URL = "https://sideeffects69.github.io/Magic-Apply-Jobs/"


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
        self._capture = None            # what the next text belongs to
        self._buffer = []
        self._details = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "meta":
            key = attrs.get("name") or attrs.get("property")
            if key:
                self.meta[key] = attrs.get("content", "")
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "title":
            self._start("title")
        elif tag == "script" and attrs.get("type") == "application/ld+json":
            self._start("jsonld")
        elif tag == "details" and "faq" in (attrs.get("class") or "").split():
            self._details = {"q": "", "a": ""}
        elif tag == "summary" and self._details is not None:
            self._start("question")
        elif tag == "p" and self._details is not None:
            self._start("answer")

    def handle_endtag(self, tag):
        if tag == "title" and self._capture == "title":
            self.title = _squash(self._finish())
        elif tag == "script" and self._capture == "jsonld":
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

    def _start(self, what):
        self._capture, self._buffer = what, []

    def _finish(self):
        text, self._capture, self._buffer = "".join(self._buffer), None, []
        return text


def _parse(path: Path) -> _Page:
    page = _Page()
    page.feed(path.read_text(encoding="utf-8"))
    return page


@pytest.fixture(scope="module")
def home() -> _Page:
    return _parse(DOCS / "index.html")


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:32]
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", header[16:24])


def _local_target(value: str, base: Path) -> Path | None:
    '''The file a relative link points at, or None for links that leave the site or stay on the page.'''
    if re.match(r"^(https?:|mailto:|#|data:)", value):
        return None
    return (base / value.split("#")[0].split("?")[0]).resolve()


# ---------------------------------------------------------------------------
# What search engines and link previews read
# ---------------------------------------------------------------------------
def test_the_title_and_description_fit_what_search_results_show(home):
    assert 30 <= len(home.title) <= 60, f"title is {len(home.title)} characters: {home.title!r}"
    description = home.meta["description"]
    assert 120 <= len(description) <= 160, f"description is {len(description)} characters"
    for phrase in ("free", "open-source", "LinkedIn"):
        assert phrase.lower() in (home.title + " " + description).lower(), f"{phrase!r} is what people search for"


def test_the_page_has_exactly_one_h1_a_language_and_a_canonical_address(home):
    assert home.h1_count == 1
    html_tag = next(attrs for tag, attrs in home.tags if tag == "html")
    assert html_tag.get("lang") == "en"
    canonical = [attrs["href"] for tag, attrs in home.tags if tag == "link" and attrs.get("rel") == "canonical"]
    assert canonical == [SITE_URL]
    assert "noindex" not in home.meta.get("robots", "")


def test_link_previews_have_a_real_image_at_the_size_they_announce(home):
    image = home.meta["og:image"]
    assert image.startswith(SITE_URL) and image == home.meta["twitter:image"]
    size = _png_size(DOCS / image.removeprefix(SITE_URL))
    assert size == (int(home.meta["og:image:width"]), int(home.meta["og:image:height"])) == (1200, 630)
    assert home.meta["twitter:card"] == "summary_large_image"
    assert home.meta["og:url"] == SITE_URL and home.meta["og:image:alt"]


def test_the_sitemap_lists_the_canonical_page():
    urls = [element.text for element in ET.parse(DOCS / "sitemap.xml").getroot().iter() if element.tag.endswith("}loc")]
    assert urls == [SITE_URL]


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
def _blocks(home):
    return {block["@type"]: block for block in map(json.loads, home.jsonld)}


def test_the_structured_data_describes_a_free_open_source_application(home):
    app = _blocks(home)["SoftwareApplication"]
    assert app["name"] == "Magic Apply - Jobs" and app["url"] == SITE_URL
    assert app["offers"]["price"] == "0" and app["isAccessibleForFree"] is True
    assert "mit" in app["license"].lower()
    assert "aggregateRating" not in app and "review" not in app, "never publish ratings nobody gave"
    for screenshot in app["screenshot"]:
        assert (DOCS / screenshot.removeprefix(SITE_URL)).exists(), screenshot


def test_the_faq_in_the_structured_data_matches_the_faq_on_the_page(home):
    questions = _blocks(home)["FAQPage"]["mainEntity"]
    from_json = [(_squash(q["name"]), _squash(q["acceptedAnswer"]["text"])) for q in questions]
    assert from_json == home.faq and len(home.faq) >= 5, "search engines may only show answers that are visible on the page"


# ---------------------------------------------------------------------------
# Images, links, and no third parties
# ---------------------------------------------------------------------------
def test_every_image_has_alt_text_and_the_size_of_its_file(home):
    images = [attrs for tag, attrs in home.tags if tag == "img"]
    assert len(images) >= 5
    for attrs in images:
        target = _local_target(attrs["src"], DOCS)
        assert target and target.exists(), attrs["src"]
        if target.suffix == ".png":
            assert (int(attrs["width"]), int(attrs["height"])) == _png_size(target), f"{attrs['src']}: width/height must match the file"
            assert len(attrs.get("alt", "")) >= 20, f"{attrs['src']} needs a real description"


def test_every_local_link_and_in_page_anchor_works(home):
    for tag, attrs in home.tags:
        for name in ("href", "src"):
            value = attrs.get(name)
            if not value:
                continue
            if value.startswith("#"):
                assert value[1:] in home.ids, f"{value} points at nothing"
            else:
                target = _local_target(value, DOCS)
                assert target is None or target.exists(), f"{tag} {name}={value!r} does not exist"


def test_the_site_loads_nothing_from_anywhere_else(home):
    for tag, attrs in home.tags:
        if tag == "script":
            assert attrs.get("type") == "application/ld+json", "no scripts: the site promises no tracking"
        if tag == "link" and attrs.get("rel") in ("stylesheet", "preload", "preconnect", "dns-prefetch"):
            pytest.fail(f"a link to {attrs.get('href')} would load from outside the site")
        if tag in ("img", "iframe", "video", "audio", "source"):
            assert not re.match(r"^(https?:)?//", attrs.get("src", "")), attrs


def test_every_outside_link_goes_to_the_project_or_its_licence(home):
    for tag, attrs in home.tags:
        href = attrs.get("href", "")
        if tag == "a" and re.match(r"^https?://", href):
            assert href.startswith("https://github.com/sideeffects69/Magic-Apply-Jobs"), href


# ---------------------------------------------------------------------------
# Keeping a personal name out, and not overclaiming
# ---------------------------------------------------------------------------
def test_the_maintainers_name_is_not_on_the_site_or_in_the_readme():
    for path in [*DOCS.rglob("*.html"), DOCS / "sitemap.xml", ROOT / "README.md", ROOT / "CONTRIBUTING.md"]:
        assert "abhyankar" not in path.read_text(encoding="utf-8").lower(), f"{path.name} names the maintainer"


def test_the_site_is_honest_that_it_is_a_beta_tested_on_mock_sites(home):
    text = _squash((DOCS / "index.html").read_text(encoding="utf-8")).lower()
    assert "beta" in text and "mock" in text and "not affiliated with" in text and "own risk" in text


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
