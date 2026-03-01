#!/usr/bin/env python3
"""Check absolute URLs in docassemble question/template files and fail on HTTP 404 responses."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from urllib.parse import urlparse

import requests
from docx2python import docx2python
from linkify_it import LinkifyIt
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate URLs in docassemble/*/data/questions and data/templates files"
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to scan (default: current directory)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="HTTP timeout in seconds for each URL request (default: 10)",
    )
    parser.add_argument(
        "--skip-templates",
        action="store_true",
        help="Skip scanning data/templates (default: False, scan templates)",
    )
    return parser.parse_args()


# File extensions likely to contain URLs worth checking.
_TEXT_SUFFIXES: frozenset[str] = frozenset({
    ".yml", ".yaml", ".py", ".md", ".html", ".json", ".js", ".txt", ".j2",
})

# Binary document formats to check
_DOCUMENT_SUFFIXES: frozenset[str] = frozenset({
    ".pdf", ".docx",
})

# URL prefixes to whitelist (API families and endpoints requiring authentication).
_WHITELIST_URL_PREFIXES: frozenset[str] = frozenset({
    "https://api.openai.com/v1/",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
})

_EXAMPLE_DOMAINS: frozenset[str] = frozenset({"example.com", "example.net", "example.org"})


def iter_question_files(root: pathlib.Path, check_templates: bool = True) -> Iterable[pathlib.Path]:
    questions_root = root / "docassemble"
    if not questions_root.exists():
        return

    for package_dir in questions_root.iterdir():
        if not package_dir.is_dir():
            continue

        scan_targets = [
            (package_dir / "data" / "questions", _TEXT_SUFFIXES),
        ]
        if check_templates:
            scan_targets.append(
                (package_dir / "data" / "templates", _TEXT_SUFFIXES | _DOCUMENT_SUFFIXES)
            )

        for scan_dir, allowed_suffixes in scan_targets:
            if not scan_dir.exists():
                continue
            for file_path in scan_dir.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in allowed_suffixes:
                    yield file_path


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=0,  # Don't retry on HTTP status codes; we only care about 404/410.
        backoff_factor=0.4,
        allowed_methods=frozenset({"GET"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "ALActions-da_build-url-checker/1.0 "
                "(+https://github.com/SuffolkLITLab/ALActions)"
            )
        }
    )
    return session


def is_absolute_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_reserved_example_domain(url: str) -> bool:
    """Check if URL is in a reserved example domain (RFC 2606)."""
    hostname = (urlparse(url).hostname or "").lower()
    return hostname in _EXAMPLE_DOMAINS or any(
        hostname.endswith(f".{domain}") for domain in _EXAMPLE_DOMAINS
    )


def is_whitelisted_url(url: str) -> bool:
    """Check if URL is in the whitelist (prefix-based for API families)."""
    return any(url.startswith(prefix) for prefix in _WHITELIST_URL_PREFIXES)


def extract_text_from_pdf(file_path: pathlib.Path) -> str:
    """Extract all text from a PDF file."""
    try:
        reader = PdfReader(file_path)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception as e:
        print(f"Warning: could not extract text from PDF {file_path}: {e}", file=sys.stderr)
        return ""


def extract_text_from_docx(file_path: pathlib.Path) -> str:
    """Extract all text from a DOCX file."""
    try:
        result = docx2python(file_path)
        return result.text
    except Exception as e:
        print(f"Warning: could not extract text from DOCX {file_path}: {e}", file=sys.stderr)
        return ""


def parse_url_token(raw_url: str) -> tuple[str | None, bool]:
    """Return (normalized_url, is_concatenated).

    *normalized_url* is ``None`` when the token should be skipped.
    *is_concatenated* is ``True`` when the token contains multiple URLs
    jammed together (a formatting error the caller should report).
    """
    url = raw_url.strip()
    if not url:
        return None, False

    # Only process explicit http/https URLs; skip fuzzy matches
    if not url.startswith(("http://", "https://")):
        return None, False

    # Link extraction in YAML/JS text can include trailing punctuation.
    url = url.rstrip(".,;:!?)>]}")

    # Query strings are valid. For concatenation checks, inspect only the
    # URL part before '?' so embedded URLs in query parameters don't trigger
    # false concatenation errors.
    url_without_query = url.split("?", 1)[0]
    num_schemes_in_base = len(re.findall(r"https?://", url_without_query))

    # Reject concatenated URLs like "...helphttps://..." (multiple schemes not at start)
    if num_schemes_in_base > 1:
        return None, True

    # Anything with literal quotes/angle brackets is likely a partial token.
    if any(ch in url for ch in ['"', "'", "<", ">"]):
        return None, False

    if not is_absolute_http_url(url):
        return None, False

    # If query parameters themselves include URLs (e.g. form_to_use=https://...),
    # normalize to the base URL so we don't flag nested URL parameter values.
    parsed = urlparse(url)
    if "http://" in parsed.query or "https://" in parsed.query:
        url = parsed._replace(query="", fragment="").geturl()

    return url, False


def extract_urls_from_file(file_path: pathlib.Path, linkify: LinkifyIt) -> tuple[list[str], list[str]]:
    # Extract text based on file type
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        text = extract_text_from_pdf(file_path)
    elif suffix == ".docx":
        text = extract_text_from_docx(file_path)
    else:
        # Plain text files
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Skip non-text files in questions directories.
            return [], []

    if not text:
        return [], []

    matches = linkify.match(text) or []
    found_urls: list[str] = []
    concatenated_urls: list[str] = []
    for match in matches:
        url, is_concatenated = parse_url_token(match.url)
        if is_concatenated:
            concatenated_urls.append(match.url.strip())
            continue
        if not url:
            continue
        if is_reserved_example_domain(url):
            continue
        found_urls.append(url)
    return found_urls, concatenated_urls


def collect_urls(root: pathlib.Path, check_templates: bool = True) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    linkify = LinkifyIt(options={"fuzzy_link": False})
    url_sources: dict[str, set[str]] = defaultdict(set)
    concatenated_sources: dict[str, set[str]] = defaultdict(set)
    for file_path in iter_question_files(root, check_templates=check_templates):
        rel_path = str(file_path.relative_to(root))
        urls, concatenated_urls = extract_urls_from_file(file_path, linkify)
        for url in urls:
            url_sources[url].add(rel_path)
        for bad_url in concatenated_urls:
            concatenated_sources[bad_url].add(rel_path)
    return url_sources, concatenated_sources


_DEAD_STATUS_CODES: frozenset[int] = frozenset({404, 410})


def check_urls(
    session: requests.Session, urls: Iterable[str], timeout: int
) -> tuple[list[tuple[str, int]], list[str]]:
    """Return (broken, unreachable) for the given *urls*.

    *broken* contains ``(url, status_code)`` pairs for dead pages.
    *unreachable* lists URLs that could not be fetched at all.
    """
    broken: list[tuple[str, int]] = []
    unreachable: list[str] = []
    for url in sorted(urls):
        # Skip whitelisted URLs (e.g., API endpoints requiring authentication)
        if is_whitelisted_url(url):
            continue

        try:
            # stream=True avoids downloading large response bodies; the
            # context manager ensures the connection is released promptly.
            with session.get(url, allow_redirects=True, timeout=timeout, stream=True) as response:
                if response.status_code in _DEAD_STATUS_CODES:
                    broken.append((url, response.status_code))
        except requests.RequestException as exc:
            print(f"Warning: could not check {url}: {exc}", file=sys.stderr)
            unreachable.append(url)
    return broken, unreachable


def main() -> int:
    args = parse_args()
    root = pathlib.Path(args.root).resolve()
    
    check_templates = not args.skip_templates
    url_sources, concatenated_sources = collect_urls(root, check_templates=check_templates)

    if not url_sources and not concatenated_sources:
        scope = "docassemble/*/data/questions"
        if check_templates:
            scope += " and data/templates"
        print(f"No absolute URLs found in {scope} files.")
        return 0

    has_errors = False

    if concatenated_sources:
        has_errors = True
        print("Found concatenated URLs (invalid link formatting):")
        for bad_url in sorted(concatenated_sources):
            sources = ", ".join(sorted(concatenated_sources[bad_url]))
            print(f"- {bad_url} (found in: {sources})")

    broken: list[tuple[str, int]] = []
    unreachable: list[str] = []
    
    if url_sources:
        session = build_session()
        broken, unreachable = check_urls(session, url_sources.keys(), args.timeout)

    if broken:
        has_errors = True
        print("Found URLs returning HTTP 404/410:")
        for url, status in broken:
            sources = ", ".join(sorted(url_sources[url]))
            print(f"- [{status}] {url} (found in: {sources})")

    if unreachable:
        has_errors = True
        print("Could not reach the following URLs:")
        for url in unreachable:
            sources = ", ".join(sorted(url_sources[url]))
            print(f"- {url} (found in: {sources})")

    if not has_errors:
        print(f"Checked {len(url_sources)} URLs; none returned HTTP 404/410.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
