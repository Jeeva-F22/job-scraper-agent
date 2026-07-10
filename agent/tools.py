"""Real-world I/O primitives the agent's tool-calling loops are built on.

These are generic, domain-agnostic operations (fetch a URL, search the web,
render a page, parse JSON) -- never a per-domain branch. All site-specific
decisions happen in the LLM, not here.
"""
import json
import os
import time

import requests

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_TIMEOUT = 20


def http_get(url, headers=None, timeout=_TIMEOUT):
    """Raw GET, no JS rendering. Used for robots.txt, sitemaps, JS bundles, direct API probes."""
    h = {"User-Agent": _UA}
    if headers:
        h.update(headers)
    try:
        r = requests.get(url, headers=h, timeout=timeout)
        return {
            "ok": True,
            "status": r.status_code,
            "url": r.url,
            "headers": dict(r.headers),
            "text": r.text[:200_000],
            "is_json": "application/json" in r.headers.get("content-type", ""),
        }
    except requests.RequestException as e:
        return {"ok": False, "status": None, "error": str(e)}


def _normalize_params(params):
    """requests serializes Python bool True/False as 'True'/'False' in query strings, which most
    JSON-flavored APIs (expecting the literal 'true'/'false') silently ignore. Normalize before sending."""
    if not params:
        return params
    return {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in params.items()}


def http_get_json(url, headers=None, params=None, timeout=_TIMEOUT):
    h = {"User-Agent": _UA, "Accept": "application/json"}
    if headers:
        h.update(headers)
    params = _normalize_params(params)
    try:
        r = requests.get(url, headers=h, params=params, timeout=timeout)
        try:
            data = r.json()
        except ValueError:
            data = None
        return {"ok": True, "status": r.status_code, "url": r.url, "json": data, "text": None if data else r.text[:5000]}
    except requests.RequestException as e:
        return {"ok": False, "status": None, "error": str(e)}


def http_post_json(url, body=None, headers=None, timeout=_TIMEOUT):
    h = {"User-Agent": _UA, "Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        h.update(headers)
    try:
        r = requests.post(url, json=body or {}, headers=h, timeout=timeout)
        try:
            data = r.json()
        except ValueError:
            data = None
        return {"ok": True, "status": r.status_code, "json": data, "text": None if data else r.text[:5000]}
    except requests.RequestException as e:
        return {"ok": False, "status": None, "error": str(e)}


def serpapi_search(query, num=10):
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        return {"ok": False, "error": "SERPAPI_KEY not set", "results": []}
    try:
        r = requests.get(
            "https://serpapi.com/search.json",
            params={"q": query, "num": num, "api_key": key},
            timeout=_TIMEOUT,
        )
        data = r.json()
        results = [
            {"title": it.get("title"), "link": it.get("link"), "snippet": it.get("snippet")}
            for it in data.get("organic_results", [])
        ]
        return {"ok": True, "results": results}
    except requests.RequestException as e:
        return {"ok": False, "error": str(e), "results": []}


def firecrawl_scrape(url, render_js=True, formats=None, timeout=_TIMEOUT * 2):
    """Rendered fetch via Firecrawl: gives markdown/html/links for JS-heavy pages."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    formats = formats or ["markdown", "html", "links"]
    if not key:
        return {"ok": False, "error": "FIRECRAWL_API_KEY not set"}
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"url": url, "formats": formats, "onlyMainContent": False, "waitFor": 1500 if render_js else 0},
            timeout=timeout,
        )
        data = r.json()
        if not data.get("success"):
            return {"ok": False, "error": data.get("error", "firecrawl failure"), "status": r.status_code}
        d = data.get("data", {})
        return {
            "ok": True,
            "markdown": (d.get("markdown") or "")[:100_000],
            "html": (d.get("html") or "")[:150_000],
            "links": d.get("links", [])[:500],
            "metadata": d.get("metadata", {}),
        }
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}


def firecrawl_scrape_interactive(url, wait_ms=3000, scroll_times=3, timeout=_TIMEOUT * 3):
    """Rendered fetch with scroll+wait actions -- surfaces AJAX/infinite-scroll-loaded
    content that a plain render pass (waitFor only) misses. Generic, not site-specific:
    applicable to any SPA/search-widget/infinite-scroll page."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return {"ok": False, "error": "FIRECRAWL_API_KEY not set"}
    actions = [{"type": "wait", "milliseconds": wait_ms}]
    for _ in range(scroll_times):
        actions.append({"type": "scroll", "direction": "down"})
        actions.append({"type": "wait", "milliseconds": 1200})
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown", "html", "links"], "onlyMainContent": False, "actions": actions},
            timeout=timeout,
        )
        data = r.json()
        if not data.get("success"):
            return {"ok": False, "error": data.get("error", "firecrawl failure"), "status": r.status_code}
        d = data.get("data", {})
        return {
            "ok": True,
            "markdown": (d.get("markdown") or "")[:100_000],
            "html": (d.get("html") or "")[:150_000],
            "links": d.get("links", [])[:500],
            "metadata": d.get("metadata", {}),
        }
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}


def firecrawl_search(query, limit=8):
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return {"ok": False, "error": "FIRECRAWL_API_KEY not set", "results": []}
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/search",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"query": query, "limit": limit},
            timeout=_TIMEOUT,
        )
        data = r.json()
        results = [
            {"title": it.get("title"), "link": it.get("url"), "snippet": it.get("description")}
            for it in data.get("data", [])
        ]
        return {"ok": True, "results": results}
    except requests.RequestException as e:
        return {"ok": False, "error": str(e), "results": []}


def robots_txt(domain):
    return http_get(f"https://{domain}/robots.txt")


def sitemap_xml(domain, path="/sitemap.xml"):
    return http_get(f"https://{domain}{path}")


def parse_html(html):
    """Parse HTML with lxml, falling back to html.parser when lxml silently drops content.
    lxml's recovery mode can discard whole subtrees on some real-world pages (seen on Zoho Recruit:
    lxml returned ZERO <input> elements from a page whose raw text contained four, one holding the
    entire job list as embedded JSON). Detect that loss by comparing raw-tag counts vs parsed counts
    and reparse with the slower but lossless html.parser."""
    from bs4 import BeautifulSoup
    html = html or ""
    soup = BeautifulSoup(html, "lxml")
    for tag in ("input", "script", "a"):
        raw_count = html.count("<" + tag)
        if raw_count >= 2 and len(soup.find_all(tag)) < raw_count // 2:
            return BeautifulSoup(html, "html.parser")
    return soup


_NOISE_CLASS_HINTS = ("header", "footer", "nav", "menu", "cookie", "consent", "flyout",
                      "breadcrumb", "social", "share", "banner", "subscribe", "newsletter",
                      "skip", "search-form", "megamenu", "sitemap")


def clean_html_for_llm(html, max_chars=20000):
    """Strip scripts/styles/head AND site chrome (nav/header/footer/menus), keeping tags+class/id so an LLM
    can see the real DOM structure and pick correct CSS selectors. Prefers the main content region so the
    truncation window centers on actual job content, not boilerplate."""
    try:
        from bs4 import BeautifulSoup  # noqa: F401
    except ImportError:
        return html[:max_chars]
    soup = parse_html(html)
    for tag in soup(["script", "style", "noscript", "svg", "path", "head", "link", "meta",
                     "header", "footer", "nav"]):
        tag.decompose()
    # drop elements whose class/id strongly signals site chrome (menus, cookie banners, etc.)
    # collect first, then decompose -- decomposing during iteration can orphan later matches.
    to_drop = []
    for el in soup.select("[class], [id]"):
        cls = el.get("class") or []
        ident = " ".join(list(cls) + [el.get("id") or ""]).lower()
        if any(h in ident for h in _NOISE_CLASS_HINTS):
            to_drop.append(el)
    for el in to_drop:
        if el is not None:
            el.decompose()
    # prefer a main content container so the job content lands early in the (truncated) output
    root = (soup.find("main")
            or soup.find(attrs={"class": lambda c: c and "site-content" in " ".join(c)})
            or soup.find(attrs={"class": lambda c: c and any(k in " ".join(c) for k in ("content", "main", "article", "job"))})
            or soup.body or soup)
    text = root.prettify()
    lines = [ln.rstrip() for ln in text.splitlines()]
    compact = "\n".join(ln for ln in lines if ln.strip())
    return compact[:max_chars]


def ldjson_blocks(html):
    """Return parsed application/ld+json blocks (schema.org structured data) from a page."""
    try:
        from bs4 import BeautifulSoup  # noqa: F401
    except ImportError:
        return []
    out = []
    soup = parse_html(html)
    for s in soup.select('script[type="application/ld+json"]'):
        try:
            out.append(json.loads(s.string or ""))
        except (json.JSONDecodeError, TypeError):
            pass
    return out


def extract_json_blobs(html, markers=("__NEXT_DATA__", "__NUXT__", "__INITIAL_STATE__", "window.__APOLLO_STATE__")):
    """Find inline JSON blobs: (a) hydration blobs by marker string + bracket-match, and
    (b) JSON stashed in hidden <input value="..."> elements (Zoho Recruit-style career sites embed
    the ENTIRE job list this way, HTML-escaped, invisible to link/selector-based extraction).
    No regex anywhere."""
    found = {}
    # (b) hidden-input JSON -- checked first since it's fully structured when present
    try:
        soup = parse_html(html)
        for inp in soup.find_all("input"):
            val = inp.get("value") or ""
            if len(val) < 100 or (not val.lstrip().startswith("[") and not val.lstrip().startswith("{")):
                continue
            try:
                data = json.loads(val)
            except json.JSONDecodeError:
                continue
            items = data if isinstance(data, list) else [data]
            if items and isinstance(items[0], dict) and len(items[0]) >= 3:
                key = f"hidden_input:{inp.get('id') or inp.get('name') or 'unnamed'}"
                found[key] = data
    except Exception:
        pass
    for marker in markers:
        idx = html.find(marker)
        if idx == -1:
            continue
        brace_start = html.find("{", idx)
        if brace_start == -1:
            continue
        depth = 0
        end = None
        for i in range(brace_start, min(len(html), brace_start + 300_000)):
            c = html[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end:
            raw = html[brace_start:end]
            try:
                found[marker] = json.loads(raw)
            except json.JSONDecodeError:
                found[marker] = {"_raw_preview": raw[:1000]}
    return found
