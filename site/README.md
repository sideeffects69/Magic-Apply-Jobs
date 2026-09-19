# The website's sources

The public website (https://sideeffects69.github.io/Magic-Apply-Jobs/) is served by GitHub Pages from the `docs/` folder. **Do not edit
the generated pages in `docs/` by hand**: edit the sources here and rebuild.

| File | What it holds |
|------|---------------|
| `pages.py` | Every page's title, description, dates, related pages, and the shared FAQ answers. Titles must be at most 60 characters and descriptions 120 to 160. |
| `content/*.html` | The body of each page (`home.html`, `how-to.html`, ...). Use `{{link:slug}}` for links between pages, `{{base}}` for assets, and `{{RELEASES}}`, `{{REPO}}` and the other tokens listed in `build.py`. |
| `template.html` | The page shell: head, Open Graph and Twitter tags, structured data slot. |
| `build.py` | Renders `docs/` (pages, `sitemap.xml`, and the HTML site map). |
| `root-domain/` | Files that belong at the root of `sideeffects69.github.io` (`robots.txt`, `llms.txt`, a landing page). They are copied to the repository of that name, because crawlers only read `robots.txt` from the root of a domain. |

```bash
python site/build.py           # write docs/
python site/build.py --check   # fail if docs/ is out of date
python -m pytest tests/test_site.py tests/test_root_domain.py
```

The tests pin the essentials: title and description sizes, one H1 per page, canonical addresses, a sitemap that matches the pages,
FAQ data that matches the visible FAQ, working links, nothing loaded from other sites, honest wording about risk, and no personal
name. `docs/googleaf5a94a2037edb13.html` proves ownership to Google Search Console: never delete or edit it.

When the numbers on a page change (the daily cap, a setting name, the version), change them in `pages.py` or the content file, bump
the page's `updated` date, rebuild, and republish. Screenshots in `docs/assets/` use made-up data; retake them if the control panel
changes, and never from real data.
