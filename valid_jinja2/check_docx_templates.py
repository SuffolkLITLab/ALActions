#!/usr/bin/env python3
"""Validate DOCX templates for Jinja syntax and emit HTML/Markdown reports."""

from __future__ import annotations

import argparse
import html
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import List, Optional, Sequence, Tuple

from validate_docx import get_jinja_errors_with_warnings, ValidationResult

# The well-known Git empty tree object SHA-1 hash. GitHub may pass an all-zero base SHA
# (0000000000000000000000000000000000000000) in several scenarios:
# - Initial commit or first push to a branch
# - New branches where no "before" state exists
# - Some push/PR events where the base is undefined
# Diffing against the empty tree allows us to list all added files without crashing.
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate DOCX templates for Jinja errors")
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
        default="jinja_validation",
        help="Directory to store generated HTML artifacts (default: jinja_validation)",
    )
    parser.add_argument(
        "--summary",
        default="jinja_validation_summary.md",
        help="Path to a Markdown summary file (default: jinja_validation_summary.md)",
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
    # Get both changed and newly added files. If base is the all-zero SHA (e.g., initial commit),
    # compare against the empty tree so the diff works.
    base_ref = base.strip() if base else ""
    if base_ref == "0" * 40:
        base_ref = EMPTY_TREE_SHA

    try:
        stdout = run_git("diff", "--name-only", "--diff-filter=AM", base_ref, head, "--", "*.docx")
    except RuntimeError as err:
        # Fallback: if diff failed (e.g., unknown base), try against the empty tree as a best effort.
        if base_ref != EMPTY_TREE_SHA:
            stdout = run_git(
                "diff", "--name-only", "--diff-filter=AM", EMPTY_TREE_SHA, head, "--", "*.docx"
            )
        else:
            raise err
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


def extract_jinja_expressions(message: str) -> Sequence[str]:
    import re

    pattern = re.compile(r"({[{%].+?[}%]})")
    return list(dict.fromkeys(match.strip() for match in pattern.findall(message)))


def validate_bytes(content: bytes) -> ValidationResult:
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        return get_jinja_errors_with_warnings(tmp_path)
    finally:
        try:
            pathlib.Path(tmp_path).unlink()
        except FileNotFoundError:
            pass


def write_file_report(
    output_dir: pathlib.Path, file_path: pathlib.Path, message: str, expressions: Sequence[str]
) -> None:
    ensure_dir(output_dir / file_path.parent)
    html_path = output_dir / file_path.with_suffix(".html")
    
    # Determine if this is errors, warnings, or both
    has_errors = "ERRORS:" in message
    has_warnings = "WARNINGS:" in message
    
    if has_errors and has_warnings:
        title = f"Jinja validation issues in {file_path}"
    elif has_errors:
        title = f"Invalid Jinja expressions in {file_path}"
    else:
        title = f"Jinja validation warnings in {file_path}"

    list_items = "\n".join(
        f"      <li><code>{html.escape(expr)}</code></li>" for expr in expressions
    ) or "      <li>No Jinja expression could be parsed from the validation output.</li>"

    body = f"""<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\">
    <title>{html.escape(title)}</title>
    <style>
      body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; }}
      pre {{ background: #f6f8fa; padding: 1rem; border-radius: 0.5rem; overflow-x: auto; }}
      code {{ font-family: ui-monospace, SFMono-Regular, SFMono, Menlo, Consolas, 'Liberation Mono', monospace; }}
      h1 {{ font-size: 1.8rem; margin-bottom: 1rem; }}
      h2 {{ margin-top: 2rem; font-size: 1.4rem; }}
      ul {{ margin-top: 0.75rem; }}
      .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 1rem; border-radius: 0.5rem; }}
      .error {{ background: #f8d7da; border: 1px solid #f5c6cb; padding: 1rem; border-radius: 0.5rem; }}
    </style>
  </head>
  <body>
    <h1>{html.escape(title)}</h1>
    <h2>Validation output</h2>
    <pre>{html.escape(message)}</pre>
    <h2>Expressions referenced</h2>
    <ul>
{list_items}
    </ul>
  </body>
</html>
"""

    html_path.write_text(body, encoding="utf-8")


def main() -> None:
    args = parse_args()
    base, head = determine_refs(args.base, args.head)

    output_dir = pathlib.Path(args.output_dir)
    summary_path = pathlib.Path(args.summary)
    changed = list_changed_docx(base, head)

    if not changed:
        message = "No DOCX files added or changed between the selected revisions."
        print(message)
        summary_path.write_text(message + "\n", encoding="utf-8")
        return

    summary_lines: List[str] = ["# DOCX Jinja validation", ""]
    html_index: List[str] = [
        "<h1>DOCX Jinja validation results</h1>",
        "<p>Only DOCX files with detected Jinja issues are listed below.</p>",
        "<ul>",
    ]

    invalid_files = 0
    missing_in_head: List[str] = []

    for file in changed:
        file_path = pathlib.Path(file)
        head_bytes = read_file_at(head, file)
        if head_bytes is None:
            missing_in_head.append(file)
            print(f"Skipping {file}: not present in head {head}")
            continue

        try:
            validation_result = validate_bytes(head_bytes)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            validation_result = ValidationResult()
            validation_result.add_syntax_error(f"Validation crashed: {exc}")

        error_message = validation_result.get_error_message()
        warnings_message = validation_result.get_warnings_message()

        if error_message or warnings_message:
            # Count as invalid only if there are actual errors (not just warnings)
            if error_message:
                invalid_files += 1
            
            # Combine error and warning messages for reporting
            combined_message = []
            if error_message:
                combined_message.append("ERRORS:")
                combined_message.append(error_message)
            if warnings_message:
                combined_message.append("WARNINGS:")
                combined_message.append(warnings_message)
            
            full_message = "\n\n".join(combined_message)
            expressions = extract_jinja_expressions(full_message)
            write_file_report(output_dir, file_path, full_message, expressions)

            html_index.append(
                f"  <li><a href='{html.escape(str(file_path.with_suffix('.html')))}'>{html.escape(str(file_path))}</a></li>"
            )

            summary_lines.append(f"## {file}")
            
            if error_message and warnings_message:
                summary_lines.append("Invalid Jinja expressions detected with warnings.")
            elif error_message:
                summary_lines.append("Invalid Jinja expressions detected.")
            else:
                summary_lines.append("Warnings detected (unknown filters).")
            
            if expressions:
                summary_lines.append("```")
                summary_lines.extend(expressions)
                summary_lines.append("```")
            
            if error_message:
                summary_lines.append("")
                summary_lines.append("<details>")
                summary_lines.append("<summary>Error output</summary>")
                summary_lines.append("")
                summary_lines.append("```")
                summary_lines.append(error_message)
                summary_lines.append("```")
                summary_lines.append("")
                summary_lines.append("</details>")
            
            if warnings_message:
                summary_lines.append("")
                summary_lines.append("<details>")
                summary_lines.append("<summary>Warnings</summary>")
                summary_lines.append("")
                summary_lines.append("```")
                summary_lines.append(warnings_message)
                summary_lines.append("```")
                summary_lines.append("")
                summary_lines.append("</details>")
            
            summary_lines.append("")
            
            # Print detailed information to the action log
            if error_message and warnings_message:
                print(f"{file}: ERRORS AND WARNINGS")
                print("=" * 50)
                print("ERRORS:")
                print(error_message)
                print("\nWARNINGS:")
                print(warnings_message)
                print("=" * 50)
            elif error_message:
                print(f"{file}: ERRORS")
                print("=" * 50)
                print(error_message)
                print("=" * 50)
            else:
                print(f"{file}: WARNINGS")
                print("=" * 50)
                print(warnings_message)
                print("=" * 50)
        else:
            print(f"{file}: OK")

    html_index.append("</ul>")

    if invalid_files == 0:
        summary_lines.append("No invalid Jinja expressions detected in added or changed DOCX files.")
    else:
        summary_lines.insert(2, f"{invalid_files} file(s) contain invalid Jinja expressions.")
        summary_lines.insert(3, "")

    if missing_in_head:
        summary_lines.append("")
        summary_lines.append("### Skipped files")
        summary_lines.append("> The following DOCX files were not present in the head revision and were skipped:")
        for item in missing_in_head:
            summary_lines.append(f"- {item}")

    # Only create HTML artifacts if there are issues to report
    # (any files were added to html_index beyond the header and closing tag)
    has_issues = len(html_index) > 3  # More than just header, opening <ul>, and closing </ul>
    if has_issues:
        ensure_dir(output_dir)
        (output_dir / "index.html").write_text("\n".join(html_index), encoding="utf-8")
    
    summary_path.write_text("\n".join(summary_lines).strip() + "\n", encoding="utf-8")

    if invalid_files > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
