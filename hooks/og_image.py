"""
MkDocs hook: expose each post's first image as `page.meta.og_image`, resolved
to an absolute URL, for use as the OpenGraph / Twitter Card image.

Posts that contain no image leave `og_image` unset; the theme override then
omits the image meta tags entirely.
"""
import re
from urllib.parse import urljoin

# First markdown image: ![alt](url) — url may be wrapped in <...>.
_IMG_MD = re.compile(r"!\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)")
# ...or an inline <img src="url">.
_IMG_HTML = re.compile(r"""<img[^>]+\bsrc\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def on_page_markdown(markdown, page, config, files):
    match = _IMG_MD.search(markdown) or _IMG_HTML.search(markdown)
    if not match:
        return markdown

    src = match.group(1).strip().strip("<>")
    if not src:
        return markdown

    if src.startswith(("http://", "https://")):
        page.meta["og_image"] = src
    else:
        site_url = config.site_url or ""
        if src.startswith("/"):
            # Root-absolute path (e.g. /assets/foo.png) -> join with site root.
            page.meta["og_image"] = urljoin(site_url, src.lstrip("/"))
        else:
            # Page-relative path -> resolve against the page's own URL.
            page.meta["og_image"] = urljoin(page.canonical_url or site_url, src)

    return markdown
