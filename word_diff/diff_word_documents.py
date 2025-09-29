#!/usr/bin/env python3
"""Generate diffs for DOCX files using docx2python.

The script compares Word documents between two git revisions, converts them to
Markdown-like text without forced line wrapping, and emits both unified and
HTML side-by-side diffs. Designed for use inside GitHub Actions so the diffs
appear in logs, the step summary, and as downloadable artifacts.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import pathlib
import subprocess
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from docx2python import docx2python
from docx2python.depth_collector import Par, Run


@dataclass
class DocxMarkdown:
    path: pathlib.Path
    markdown: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate DOCX diffs")
    parser.add_argument(
        "--base",
        help="Base git ref/sha for comparison (default: auto-detected)",
    )
    parser.add_argument(
        "--head",
        help="Head git ref/sha for comparison (default: current GitHub SHA)",
    )
    parser.add_argument(
        "--output-dir",
        default="word_diffs",
        help="Directory to store diff artifacts (default: word_diffs)",
    )
    parser.add_argument(
        "--summary",
        default="word_diff_summary.md",
        help="Path to a Markdown summary file",
    )
    return parser.parse_args()


def run_git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed with code {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def list_changed_docx(base: str, head: str) -> List[str]:
    stdout = run_git("diff", "--name-only", base, head, "--", "*.docx")
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def file_exists_at(ref: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def read_file_at(ref: str, path: str) -> Optional[bytes]:
    if not file_exists_at(ref, path):
        return None
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        check=True,
    )
    return result.stdout


def normalize_whitespace(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def flatten_strings(node: Sequence | str) -> Iterator[str]:
    if isinstance(node, str):
        cleaned = normalize_whitespace(node)
        if cleaned:
            yield cleaned
        return
    for item in node:
        if isinstance(item, (list, tuple)):
            yield from flatten_strings(item)
        else:
            text = normalize_whitespace(str(item))
            if text:
                yield text


def iter_paragraphs(structure: Sequence) -> Iterator[Par]:
    stack: List = list(structure)[::-1]
    while stack:
        item = stack.pop()
        if isinstance(item, Par):
            yield item
        elif isinstance(item, list):
            stack.extend(item[::-1])


def block_is_table(block_pars: Sequence) -> bool:
    return any("tbl" in (par.lineage or ()) for par in iter_paragraphs(block_pars))


def run_to_markdown(run: Run) -> str:
    text = normalize_whitespace(run.text)
    if not text:
        return ""

    styles = set(run.html_style or [])
    prefix = suffix = ""
    if "b" in styles and "i" in styles:
        prefix = suffix = "***"
    elif "b" in styles:
        prefix = suffix = "**"
    elif "i" in styles:
        prefix = suffix = "*"
    elif "u" in styles:
        prefix = suffix = "__"

    return f"{prefix}{text}{suffix}"


def paragraph_to_markdown(paragraph: Par) -> str:
    pieces = [piece for piece in (run_to_markdown(run) for run in paragraph.runs) if piece]
    text = " ".join(pieces).strip()
    if not text:
        return ""

    style = (paragraph.style or "").lower()
    if style.startswith("heading"):
        digits = "".join(ch for ch in paragraph.style if ch.isdigit())
        level = int(digits) if digits.isdigit() else 1
        level = max(1, min(level, 6))
        return f"{'#' * level} {text}"
    if "list" in style:
        prefix = "- "
        if "number" in style or "decimal" in style:
            prefix = "1. "
        return f"{prefix}{text}"

    return text


def table_block_to_markdown(block: Sequence[Sequence]) -> str:
    table_rows: List[List[str]] = []
    for row in block:
        cells: List[str] = []
        for cell in row:
            cell_text = " ".join(flatten_strings(cell)).strip()
            cells.append(cell_text)
        if cells:
            table_rows.append(cells)

    if not table_rows:
        return ""

    width = max(len(row) for row in table_rows)
    for row in table_rows:
        if len(row) < width:
            row.extend([""] * (width - len(row)))

    header = table_rows[0]
    divider = "| " + " | ".join(["---"] * width) + " |"
    md_lines = ["| " + " | ".join(header) + " |", divider]
    for row in table_rows[1:]:
        md_lines.append("| " + " | ".join(row) + " |")
    return "\n".join(md_lines)


def convert_docx_to_markdown(data: bytes, file_path: str) -> DocxMarkdown:
    lines: List[str] = []
    with docx2python(BytesIO(data), html=True) as document:
        for block, block_pars in zip(document.body, document.body_pars):
            if block_is_table(block_pars):
                table_md = table_block_to_markdown(block)
                if table_md:
                    lines.append(table_md)
                continue

            for paragraph in iter_paragraphs(block_pars):
                md = paragraph_to_markdown(paragraph)
                if md:
                    lines.append(md)

    markdown = "\n\n".join(lines).strip()
    return DocxMarkdown(path=pathlib.Path(file_path), markdown=markdown)


def unified_diff(label: str, base_md: Optional[str], head_md: Optional[str]) -> str:
    from difflib import unified_diff as udiff

    base_lines = (base_md or "").splitlines()
    head_lines = (head_md or "").splitlines()
    diff = udiff(base_lines, head_lines, fromfile=f"a/{label}", tofile=f"b/{label}", lineterm="")
    return "\n".join(diff)


def html_diff(label: str, base_md: Optional[str], head_md: Optional[str]) -> str:
    from difflib import HtmlDiff

    base_lines = (base_md or "").splitlines()
    head_lines = (head_md or "").splitlines()
    return HtmlDiff(wrapcolumn=160).make_file(base_lines, head_lines, f"a/{label}", f"b/{label}")


def ensure_dir(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def determine_refs(base_arg: Optional[str], head_arg: Optional[str]) -> Tuple[str, str]:
    head = head_arg or os.environ.get("GITHUB_SHA")
    base = base_arg or os.environ.get("INPUT_BASE_REF")

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")

    if (not base or base == "") and event_path and pathlib.Path(event_path).exists():
        with open(event_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if event_name == "pull_request":
            base = payload.get("pull_request", {}).get("base", {}).get("sha")
        elif event_name == "push":
            base = payload.get("before")
        elif event_name == "workflow_dispatch":
            inputs = payload.get("inputs", {})
            base = inputs.get("base") or payload.get("before")
            head = inputs.get("head") or head

    if not head:
        head = run_git("rev-parse", "HEAD").strip()

    if not base:
        base = run_git("rev-parse", "HEAD^1").strip()

    return base, head


def main() -> None:
    args = parse_args()
    base, head = determine_refs(args.base, args.head)

    output_dir = pathlib.Path(args.output_dir)
    ensure_dir(output_dir)

    summary_path = pathlib.Path(args.summary)
    changed = list_changed_docx(base, head)

    if not changed:
        message = "No DOCX changes detected between the selected revisions."
        print(message)
        summary_path.write_text(message + "\n", encoding="utf-8")
        return

    summary_lines: List[str] = ["# Word document diffs", ""]
    html_index: List[str] = ["<h1>Word document diffs</h1>", "<p>Markdown conversion diff results.</p>", "<ul>"]

    for file in changed:
        base_bytes = read_file_at(base, file)
        head_bytes = read_file_at(head, file)

        base_md = convert_docx_to_markdown(base_bytes, file).markdown if base_bytes else None
        head_md = convert_docx_to_markdown(head_bytes, file).markdown if head_bytes else None

        diff_text = unified_diff(file, base_md, head_md)
        diff_path = output_dir / f"{file}.diff"
        ensure_dir(diff_path.parent)
        diff_path.write_text(diff_text + "\n", encoding="utf-8")

        html_body = html_diff(file, base_md, head_md)
        html_path = output_dir / f"{file}.html"
        html_path.write_text(html_body, encoding="utf-8")

        if base_md is not None:
            (output_dir / f"{file}.base.md").write_text(base_md + "\n", encoding="utf-8")
        if head_md is not None:
            (output_dir / f"{file}.head.md").write_text(head_md + "\n", encoding="utf-8")

        print(f"\n===== Diff for {file} =====")
        if diff_text.strip():
            print(diff_text)
        else:
            print("No textual differences detected after conversion.")

        summary_lines.append(f"## {file}")
        summary_lines.append("````diff")
        summary_lines.append(diff_text or "No differences detected")
        summary_lines.append("````")
        summary_lines.append("")

        html_index.append(
            f"  <li><a href='{html.escape(file)}.html'>{html.escape(file)}</a></li>"
        )

    html_index.append("</ul>")
    (output_dir / "index.html").write_text("\n".join(html_index), encoding="utf-8")
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

