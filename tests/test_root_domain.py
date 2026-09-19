"""
The files that belong at the root of sideeffects69.github.io (kept in site/root-domain/ and copied to the repository of that name):
robots.txt, llms.txt and a small landing page. Crawlers read robots.txt only from the root of a domain, so it cannot live in the
project site. The maintainer wants every search engine and every AI crawler to be able to read the site; these tests keep it that way.
"""

import importlib.util
import re
import sys
from pathlib import Path
from urllib.robotparser import RobotFileParser

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ROOT_DOMAIN = ROOT / "site" / "root-domain"
SITE_URL = "https://sideeffects69.github.io/Magic-Apply-Jobs/"


def _pages():
    spec = importlib.util.spec_from_file_location("magic_root_pages", ROOT / "site" / "pages.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["magic_root_pages"] = module
    spec.loader.exec_module(module)
    return module


PAGES = _pages()

CRAWLERS = ["Googlebot", "Bingbot", "DuckDuckBot", "Applebot", "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User",
            "Claude-SearchBot", "anthropic-ai", "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended", "CCBot",
            "Meta-ExternalAgent", "Amazonbot", "cohere-ai", "MistralAI-User", "Bytespider", "SomeCrawlerNobodyHasHeardOf"]


def _robots() -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse((ROOT_DOMAIN / "robots.txt").read_text(encoding="utf-8").splitlines())
    return parser


@pytest.mark.parametrize("crawler", CRAWLERS)
def test_every_crawler_including_the_ai_ones_may_read_the_whole_site(crawler):
    robots = _robots()
    for page in PAGES.PAGES:
        assert robots.can_fetch(crawler, PAGES.url(page["slug"])), f"{crawler} is blocked from {page['slug'] or 'the home page'}"
    assert robots.can_fetch(crawler, SITE_URL + "assets/screenshot-run.png") and robots.can_fetch(crawler, SITE_URL + "sitemap.xml")


def test_robots_txt_never_blocks_anything():
    text = (ROOT_DOMAIN / "robots.txt").read_text(encoding="utf-8")
    assert not re.search(r"(?im)^\s*Disallow:\s*\S", text), "a Disallow rule would hide part of the site from crawlers"
    assert not re.search(r"(?im)^\s*Crawl-delay", text), "a crawl delay would slow the crawlers the maintainer wants to welcome"


def test_robots_txt_names_the_main_ai_crawlers_and_points_at_the_sitemap():
    text = (ROOT_DOMAIN / "robots.txt").read_text(encoding="utf-8")
    for agent in ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "PerplexityBot", "Google-Extended", "Applebot-Extended", "CCBot"):
        assert re.search(rf"(?im)^User-agent:\s*{re.escape(agent)}\s*$", text), f"{agent} should be named"
    assert _robots().site_maps() == [SITE_URL + "sitemap.xml"]
    assert (DOCS / "sitemap.xml").exists()


def test_llms_txt_links_to_real_pages_and_lists_every_guide():
    text = (ROOT_DOMAIN / "llms.txt").read_text(encoding="utf-8")
    assert text.startswith("# Magic Apply - Jobs\n") and "\n> " in text, "llms.txt starts with a title and a summary"
    links = re.findall(r"\]\((https://[^)]+)\)", text)
    for link in links:
        if link.startswith(SITE_URL):
            path = link.removeprefix(SITE_URL)
            assert (DOCS / path).exists() or (DOCS / path / "index.html").exists() or path == "", link
    for page in PAGES.PAGES:
        if page["kind"] in ("guide", "faq"):
            assert PAGES.url(page["slug"]) in links, f"llms.txt should list {page['slug']}"
    assert "against LinkedIn's rules" in text, "it must carry the same honesty about risk as the site"


def test_the_landing_page_points_to_the_real_site_and_stays_small():
    html = (ROOT_DOMAIN / "index.html").read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{SITE_URL}">' in html
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    description = re.search(r'<meta name="description" content="(.*?)"', html).group(1)
    assert 20 <= len(title) <= 60 and 120 <= len(description) <= 160
    assert "<script" not in html and "noindex" not in html
    for href in re.findall(r'href="(/Magic-Apply-Jobs/[^"]*)"', html):
        path = href.removeprefix("/Magic-Apply-Jobs/")
        assert (DOCS / path).exists() or (DOCS / path / "index.html").exists(), href
    assert 'name="robots" content="noindex"' in (ROOT_DOMAIN / "404.html").read_text(encoding="utf-8")


def test_the_root_files_do_not_name_the_maintainer():
    for path in ROOT_DOMAIN.iterdir():
        assert "abhyankar" not in path.read_text(encoding="utf-8").lower(), path.name
