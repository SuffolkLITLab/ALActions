#!/usr/bin/env python3
"""Check PDFs in a docassemble repository for PDF/UA-1 accessibility compliance using veraPDF."""

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------------------
# Rule severity classification
# ---------------------------------------------------------------------------
# Severity levels:
#   "info"            - administrative/metadata only; logged but no annotation
#   "warning"         - advisory; always emits a GitHub warning annotation
#   "fail"            - real accessibility blocker; emits warning or error
#                       annotation depending on PDF_ACCESSIBILITY_MODE
#   "form_annotation" - annotation structure / tab-order rules that only
#                       matter when forms are not flattened; treated as "fail"
#                       in strict mode, suppressed (logged only) otherwise
#
# Keys are (clause, test_number) tuples matching veraPDF XML attributes.
# Unmapped rules fall back to "fail" so nothing is silently swallowed.

RULE_SEVERITY: dict[tuple[str, str], str] = {
    # §5 — PDF/UA identification in XMP metadata (administrative)
    ("5", "1"): "info",
    ("5", "2"): "info",
    ("5", "3"): "info",
    ("5", "4"): "info",
    ("5", "5"): "info",
    # §6.1 — PDF version header syntax (technical, not user-facing)
    ("6.1", "1"): "info",
    # §6.2 — MarkInfo.Marked=true (document not tagged at all)
    ("6.2", "1"): "fail",
    # §7.1 — Content structure, metadata, and structure tree
    ("7.1", "1"):  "fail",    # Artifact nested inside tagged content
    ("7.1", "2"):  "fail",    # Tagged content nested inside Artifact
    ("7.1", "3"):  "fail",    # Real content neither tagged nor Artifact
    ("7.1", "4"):  "warning", # Suspects=true (may generate false positives)
    ("7.1", "5"):  "warning", # Non-standard type not mapped to standard type
    ("7.1", "6"):  "fail",    # Circular role map
    ("7.1", "7"):  "fail",    # Standard type remapped
    ("7.1", "8"):  "warning", # No XMP metadata stream
    ("7.1", "9"):  "warning", # Missing dc:title in XMP
    ("7.1", "10"): "warning", # Missing DisplayDocTitle viewer preference
    ("7.1", "11"): "fail",    # Missing StructTreeRoot (document untagged)
    ("7.1", "12"): "fail",    # Structure element missing parent entry
    # §7.2 — Language (advisory) and table/list structure (real failures)
    ("7.2", "2"):  "warning", # Language for Outline entries undetermined
    ("7.2", "3"):  "fail",    # Table has invalid child elements
    ("7.2", "4"):  "fail",    # TR not contained in Table/THead/TBody/TFoot
    ("7.2", "5"):  "fail",    # THead not in Table
    ("7.2", "6"):  "fail",    # TBody not in Table
    ("7.2", "7"):  "fail",    # TFoot not in Table
    ("7.2", "8"):  "fail",    # TH not in TR
    ("7.2", "9"):  "fail",    # TD not in TR
    ("7.2", "10"): "fail",    # TR has invalid child elements
    ("7.2", "11"): "fail",    # Table has more than one THead
    ("7.2", "12"): "fail",    # Table has more than one TFoot
    ("7.2", "13"): "fail",    # Table has TFoot but no TBody
    ("7.2", "14"): "fail",    # Table has THead but no TBody
    ("7.2", "15"): "fail",    # Table cells overlap
    ("7.2", "16"): "fail",    # Table Caption not first or last child
    ("7.2", "17"): "warning", # LI not in L
    ("7.2", "18"): "warning", # LBody not in LI
    ("7.2", "19"): "warning", # L has invalid child elements
    ("7.2", "20"): "warning", # LI has invalid child elements
    ("7.2", "21"): "warning", # Language for ActualText in struct element
    ("7.2", "22"): "warning", # Language for Alt in struct element
    ("7.2", "23"): "warning", # Language for E attribute in struct element
    ("7.2", "24"): "warning", # Language for annotation Contents
    ("7.2", "25"): "warning", # Language for form field TU key
    ("7.2", "26"): "warning", # TOCI not in TOC
    ("7.2", "27"): "warning", # TOC has invalid child elements
    ("7.2", "28"): "warning", # TOC Caption not first child
    ("7.2", "29"): "warning", # Lang value not a valid Language-Tag
    ("7.2", "30"): "warning", # Language for ActualText in Span
    ("7.2", "31"): "warning", # Language for Alt in Span
    ("7.2", "32"): "warning", # Language for E in Span
    ("7.2", "33"): "warning", # Language for document metadata
    ("7.2", "34"): "warning", # Language for text in page content
    ("7.2", "36"): "fail",    # THead has invalid child elements
    ("7.2", "37"): "fail",    # TBody has invalid child elements
    ("7.2", "38"): "fail",    # TFoot has invalid child elements
    ("7.2", "39"): "fail",    # Table has more than one Caption
    ("7.2", "40"): "warning", # List Caption not first child
    ("7.2", "41"): "fail",    # Table columns span different numbers of rows
    ("7.2", "42"): "fail",    # Table rows span different numbers of columns
    ("7.2", "43"): "fail",    # Table rows span different numbers of columns (variant)
    # §7.3 — Figures
    ("7.3", "1"):  "fail",    # Figure missing Alt/ActualText
    # §7.4 — Headings
    ("7.4.2", "1"): "warning", # Heading level skipped
    ("7.4.4", "1"): "warning", # Node contains more than one H tag
    ("7.4.4", "2"): "warning", # Document mixes H and Hn tags
    ("7.4.4", "3"): "warning", # Document mixes H and Hn tags
    # §7.5 — Table header scope
    ("7.5", "1"):  "fail",    # TD has no connected header
    ("7.5", "2"):  "fail",    # TD references undefined header ID
    # §7.7 — Mathematical formulae
    ("7.7", "1"):  "fail",    # Formula missing Alt/ActualText
    # §7.9 — Notes
    ("7.9", "1"):  "warning", # Note missing ID entry
    ("7.9", "2"):  "warning", # Note has non-unique ID
    # §7.10 — Optional content (layers)
    ("7.10", "1"): "info",
    ("7.10", "2"): "info",
    # §7.11 — Embedded files
    ("7.11", "1"): "warning", # Embedded file spec missing F or UF key
    # §7.15 — XFA forms
    ("7.15", "1"): "fail",    # Dynamic XFA form present
    # §7.16 — Security / encryption
    ("7.16", "1"): "warning", # Encryption P key missing accessibility bit
    # §7.18 — Annotations and form fields
    ("7.18.1", "1"):  "fail",           # Non-widget annotation not in Annot tag
    ("7.18.1", "2"):  "fail",           # Non-widget annotation missing Contents/Alt
    ("7.18.1", "3"):  "fail",           # Form field missing accessible name (TU key)
    ("7.18.2", "1"):  "fail",           # TrapNet annotation present
    ("7.18.3", "1"):  "form_annotation", # Page with annotations missing Tabs=S
    ("7.18.4", "1"):  "form_annotation", # Widget annotation not in Form tag
    ("7.18.4", "2"):  "form_annotation", # Form element missing role or single widget child
    ("7.18.5", "1"):  "fail",           # Link annotation not in Link tag
    ("7.18.5", "2"):  "warning",        # Link annotation missing Contents description
    ("7.18.6.2", "1"): "warning",       # Media clip missing CT key
    ("7.18.6.2", "2"): "warning",       # Media clip missing Alt key
    ("7.18.8", "1"):  "info",           # PrinterMark annotation in logical structure
    # §7.20 — XObjects
    ("7.20", "1"): "info",    # Reference XObject (technically disallowed)
    ("7.20", "2"): "warning", # Form XObject with MCIDs referenced multiple times
    # §7.21 — Fonts
    ("7.21.3.1", "1"): "warning", # Type0 font CIDSystemInfo mismatch
    ("7.21.3.2", "1"): "warning", # Type2 CIDFont missing CIDToGIDMap
    ("7.21.3.3", "1"): "warning", # Non-standard CMap not embedded
    ("7.21.3.3", "2"): "warning", # Embedded CMap WMode mismatch
    ("7.21.3.3", "3"): "warning", # CMap references non-standard CMap
    ("7.21.4.1", "1"): "fail",    # Font program not embedded
    ("7.21.4.1", "2"): "fail",    # Glyph missing from embedded font
    ("7.21.4.2", "1"): "warning", # Type1 CharSet doesn't list all glyphs
    ("7.21.4.2", "2"): "warning", # CIDFont CIDSet doesn't identify all glyphs
    ("7.21.5", "1"):   "warning", # Glyph width inconsistency
    ("7.21.6", "1"):   "warning", # Non-symbolic TrueType missing non-symbolic cmap
    ("7.21.6", "2"):   "warning", # Non-symbolic TrueType encoding not MacRoman/WinAnsi
    ("7.21.6", "3"):   "warning", # Symbolic TrueType has Encoding entry
    ("7.21.6", "4"):   "warning", # Symbolic TrueType cmap issue
    ("7.21.7", "1"):   "fail",    # Glyph missing ToUnicode mapping (text unextractable)
}


def classify_rule(clause: str, test_number: str, strict: bool) -> str:
    """Return effective severity for a failed rule given the current strict setting.

    Returns "info", "warning", "fail", or "suppressed".
    """
    base = RULE_SEVERITY.get((clause, test_number), "fail")  # unknown → fail
    if base == "form_annotation":
        return "fail" if strict else "suppressed"
    return base


def find_pdfs(root_dir: Path) -> list[Path]:
    """Find all PDFs, prioritizing docassemble/*/data/templates/ directories."""
    seen: set[Path] = set()
    pdfs: list[Path] = []

    # Priority: docassemble/*/data/templates/ (standard Assembly Line template location)
    for pdf in sorted(root_dir.glob("docassemble/*/data/templates/**/*.pdf")):
        key = pdf.resolve()
        if key not in seen:
            seen.add(key)
            pdfs.append(pdf)

    # All other PDFs in the repository
    for pdf in sorted(root_dir.rglob("*.pdf")):
        key = pdf.resolve()
        if key not in seen:
            seen.add(key)
            pdfs.append(pdf)

    return pdfs


def run_verapdf(pdfs: list[Path], verapdf_cmd: str = "verapdf") -> tuple[str, str]:
    """Run veraPDF on a list of PDFs; return (stdout_xml, stderr)."""
    cmd = [verapdf_cmd, "--flavour", "ua1", "--format", "xml"] + [str(p) for p in pdfs]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result.stdout, result.stderr


def parse_results(xml_output: str) -> list[dict]:
    """Parse veraPDF XML output and return a list of per-PDF result dicts."""
    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError as e:
        return [{"pdf": "unknown", "compliant": False, "parse_error": str(e), "failed_rules": []}]

    results = []
    for job in root.findall(".//job"):
        item = job.find("item")
        name_el = item.find("name") if item is not None else None
        pdf_name = name_el.text or "unknown" if name_el is not None else "unknown"

        task_exc = job.find("taskException")
        if task_exc is not None:
            msg_el = task_exc.find("exceptionMessage")
            msg = (msg_el.text or "Unknown error").strip() if msg_el is not None else "Unknown error"
            results.append({
                "pdf": pdf_name,
                "compliant": False,
                "exception": msg,
                "failed_rules": [],
            })
            continue

        report = job.find("validationReport")
        if report is None:
            results.append({
                "pdf": pdf_name,
                "compliant": False,
                "exception": "No validation report in veraPDF output",
                "failed_rules": [],
            })
            continue

        is_compliant = report.get("isCompliant", "false").lower() == "true"
        failed_rules = []

        if not is_compliant:
            for rule in report.findall(".//rule[@status='failed']"):
                desc_el = rule.find("description")
                description = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                clause = rule.get("clause", "")
                test_number = rule.get("testNumber", "")
                failed_rules.append({
                    "specification": rule.get("specification", ""),
                    "clause": clause,
                    "test_number": test_number,
                    "description": description,
                    "failed_checks": int(rule.get("failedChecks", 0)),
                    # base_severity is set here; effective severity depends on strict mode
                    "base_severity": RULE_SEVERITY.get((clause, test_number), "fail"),
                })

        results.append({
            "pdf": pdf_name,
            "compliant": is_compliant,
            "failed_rules": failed_rules,
        })

    return results


def emit_annotation(level: str, title: str, message: str) -> None:
    """Emit a GitHub Actions workflow command annotation."""
    encoded = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{level} title={title}::{encoded}", flush=True)


def write_summary(results: list[dict], strict: bool) -> None:
    """Append a Markdown section to the GitHub Actions job summary."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    total = len(results)
    lines = ["## PDF Accessibility Check (PDF/UA-1)", ""]

    if total == 0:
        lines.append("_No PDFs found in repository._")
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return

    # Classify every failed rule with its effective severity
    def effective_rules(result: dict) -> dict[str, list[dict]]:
        """Return rules bucketed by effective severity for a single result."""
        buckets: dict[str, list[dict]] = {"fail": [], "warning": [], "info": [], "suppressed": []}
        for rule in result.get("failed_rules", []):
            sev = classify_rule(rule["clause"], rule["test_number"], strict)
            buckets[sev].append(rule)
        return buckets

    # Count PDFs with at least one fail-level issue
    fail_count = sum(
        1 for r in results
        if not r.get("compliant") and (
            r.get("exception") or r.get("parse_error")
            or any(
                classify_rule(rule["clause"], rule["test_number"], strict) == "fail"
                for rule in r.get("failed_rules", [])
            )
        )
    )
    warn_only_count = sum(
        1 for r in results
        if not r.get("compliant") and not r.get("exception") and not r.get("parse_error")
        and not any(
            classify_rule(rule["clause"], rule["test_number"], strict) == "fail"
            for rule in r.get("failed_rules", [])
        )
        and any(
            classify_rule(rule["clause"], rule["test_number"], strict) == "warning"
            for rule in r.get("failed_rules", [])
        )
    )

    if fail_count == 0 and warn_only_count == 0:
        lines.append(f"✅ All {total} PDF(s) passed PDF/UA-1 accessibility checks.")
    elif fail_count > 0:
        lines.append(
            f"❌ **{fail_count} of {total} PDF(s) have accessibility failures** "
            f"that require attention."
        )
        if warn_only_count > 0:
            lines.append(f"⚠️ {warn_only_count} additional PDF(s) have advisory warnings only.")
    else:
        lines.append(f"⚠️ **{warn_only_count} of {total} PDF(s) have advisory warnings.**")

    if strict:
        lines.append(
            "_Strict mode enabled: tab-order and form-annotation structure rules are active._"
        )
    else:
        lines.append(
            "_Non-strict mode: tab-order and form-annotation structure rules are suppressed "
            "(forms may be flattened before users see them). Enable with `verapdf-strict: true`._"
        )
    lines.append("")

    def _render_pdf_section(result: dict, buckets: dict[str, list[dict]]) -> list[str]:
        out = []
        pdf_path = result["pdf"]
        pdf_name = Path(pdf_path).name
        out.append(f"#### `{pdf_name}`")
        if pdf_name != pdf_path:
            out.append(f"_Path: `{pdf_path}`_")
        out.append("")

        if result.get("exception"):
            out.append(f"> ❌ **Error:** {result['exception']}")
            out.append("")
            return out
        if result.get("parse_error"):
            out.append(f"> ❌ **Parse error:** {result['parse_error']}")
            out.append("")
            return out

        def _rule_table(rule_list: list[dict]) -> list[str]:
            rows = ["| Rule | Description | Occurrences |", "|------|-------------|-------------|"]
            for rule in rule_list:
                spec = rule["specification"]
                clause = rule["clause"]
                test = rule["test_number"]
                ref = f"{spec} §{clause}" + (f".{test}" if test else "")
                desc = rule["description"].replace("|", "\\|")
                rows.append(f"| `{ref}` | {desc} | {rule['failed_checks']} |")
            return rows

        if buckets["fail"]:
            out.extend(_rule_table(buckets["fail"]))
            out.append("")
        if buckets["warning"]:
            out.append("<details><summary>Advisory warnings</summary>")
            out.append("")
            out.extend(_rule_table(buckets["warning"]))
            out.append("")
            out.append("</details>")
            out.append("")
        if buckets["suppressed"]:
            out.append(
                f"<details><summary>Suppressed (form annotation / tab order) "
                f"— {len(buckets['suppressed'])} rule(s)</summary>"
            )
            out.append("")
            out.extend(_rule_table(buckets["suppressed"]))
            out.append("")
            out.append("</details>")
            out.append("")
        if buckets["info"]:
            out.append(
                f"<details><summary>Informational — {len(buckets['info'])} rule(s)</summary>"
            )
            out.append("")
            out.extend(_rule_table(buckets["info"]))
            out.append("")
            out.append("</details>")
            out.append("")
        return out

    # Failing PDFs first
    failing_pdfs = [
        r for r in results
        if not r.get("compliant") and (
            r.get("exception") or r.get("parse_error")
            or any(
                classify_rule(rule["clause"], rule["test_number"], strict) == "fail"
                for rule in r.get("failed_rules", [])
            )
        )
    ]
    if failing_pdfs:
        lines.append("### ❌ Accessibility Failures")
        lines.append("")
        for result in failing_pdfs:
            buckets = effective_rules(result)
            lines.extend(_render_pdf_section(result, buckets))

    # Advisory-only PDFs
    warn_only_pdfs = [
        r for r in results
        if not r.get("compliant") and not r.get("exception") and not r.get("parse_error")
        and not any(
            classify_rule(rule["clause"], rule["test_number"], strict) == "fail"
            for rule in r.get("failed_rules", [])
        )
        and any(
            classify_rule(rule["clause"], rule["test_number"], strict) in ("warning", "suppressed")
            for rule in r.get("failed_rules", [])
        )
    ]
    if warn_only_pdfs:
        lines.append("### ⚠️ Advisory Warnings Only")
        lines.append("")
        for result in warn_only_pdfs:
            buckets = effective_rules(result)
            lines.extend(_render_pdf_section(result, buckets))

    # Passing PDFs
    passing = [r for r in results if r.get("compliant")]
    if passing:
        lines.append("### ✅ Passing PDFs")
        lines.append("")
        for r in passing:
            lines.append(f"- ✅ `{Path(r['pdf']).name}`")
        lines.append("")

    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    verapdf_cmd = os.environ.get("VERAPDF_CMD", "verapdf")
    failure_mode = os.environ.get("PDF_ACCESSIBILITY_MODE", "warning")
    strict = os.environ.get("PDF_ACCESSIBILITY_STRICT", "false").lower() in ("true", "1", "yes")
    root_dir = Path(os.environ.get("GITHUB_WORKSPACE", "."))

    mode_label = f"mode={failure_mode}, {'strict' if strict else 'non-strict'}"

    try:
        subprocess.run([verapdf_cmd, "--version"], capture_output=True, timeout=30, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        emit_annotation(
            "error",
            "PDF Accessibility",
            f"veraPDF not found or failed to start ({exc}). Skipping accessibility check.",
        )
        return 0  # Don't fail the build if veraPDF itself can't run

    pdfs = find_pdfs(root_dir)
    if not pdfs:
        print("No PDFs found in repository. Skipping accessibility check.", flush=True)
        write_summary([], strict)
        return 0

    print(f"Checking {len(pdfs)} PDF(s) for PDF/UA-1 accessibility ({mode_label}):", flush=True)
    for pdf in pdfs:
        try:
            rel = pdf.relative_to(root_dir)
        except ValueError:
            rel = pdf
        print(f"  {rel}", flush=True)

    xml_output, stderr = run_verapdf(pdfs, verapdf_cmd)
    if stderr:
        for line in stderr.splitlines():
            if line.strip():
                print(f"  [verapdf] {line}", flush=True)

    if not xml_output.strip():
        emit_annotation(
            "error",
            "PDF Accessibility",
            "veraPDF produced no output. Check that veraPDF installed correctly.",
        )
        return 0

    results = parse_results(xml_output)
    total = len(results)

    # Per-PDF console summary
    print("", flush=True)
    for result in results:
        name = Path(result["pdf"]).name
        if result.get("compliant"):
            print(f"  ✓ {name}: compliant", flush=True)
        elif result.get("exception") or result.get("parse_error"):
            msg = result.get("exception") or result.get("parse_error")
            print(f"  ✗ {name}: error — {msg}", flush=True)
        else:
            buckets: dict[str, int] = {"fail": 0, "warning": 0, "info": 0, "suppressed": 0}
            for rule in result["failed_rules"]:
                sev = classify_rule(rule["clause"], rule["test_number"], strict)
                buckets[sev] += 1
            parts = []
            if buckets["fail"]:
                parts.append(f"{buckets['fail']} failure(s)")
            if buckets["warning"]:
                parts.append(f"{buckets['warning']} warning(s)")
            if buckets["suppressed"]:
                parts.append(f"{buckets['suppressed']} suppressed")
            if buckets["info"]:
                parts.append(f"{buckets['info']} info")
            print(f"  ✗ {name}: {', '.join(parts) if parts else 'non-compliant'}", flush=True)

    write_summary(results, strict)

    # Collect PDFs with real failures (fail-severity violations)
    failing = [
        r for r in results
        if not r.get("compliant") and (
            r.get("exception") or r.get("parse_error")
            or any(
                classify_rule(rule["clause"], rule["test_number"], strict) == "fail"
                for rule in r.get("failed_rules", [])
            )
        )
    ]
    # Collect PDFs with advisory warnings only
    warn_only = [
        r for r in results
        if not r.get("compliant") and not r.get("exception") and not r.get("parse_error")
        and not any(
            classify_rule(rule["clause"], rule["test_number"], strict) == "fail"
            for rule in r.get("failed_rules", [])
        )
        and any(
            classify_rule(rule["clause"], rule["test_number"], strict) == "warning"
            for rule in r.get("failed_rules", [])
        )
    ]

    if failing:
        failing_names = ", ".join(Path(r["pdf"]).name for r in failing)
        total_violations = sum(
            sum(1 for rule in r.get("failed_rules", [])
                if classify_rule(rule["clause"], rule["test_number"], strict) == "fail")
            for r in failing
        )
        annotation_msg = (
            f"{len(failing)} of {total} PDF(s) have PDF/UA-1 accessibility failures: "
            f"{failing_names}. {total_violations} rule violation(s). "
            "See the job summary for details."
        )
        level = "error" if failure_mode == "error" else "warning"
        emit_annotation(level, "PDF Accessibility (PDF/UA-1)", annotation_msg)
        if failure_mode == "error":
            return 1

    elif warn_only:
        warn_names = ", ".join(Path(r["pdf"]).name for r in warn_only)
        emit_annotation(
            "warning",
            "PDF Accessibility (PDF/UA-1)",
            f"{len(warn_only)} PDF(s) have advisory accessibility warnings: {warn_names}. "
            "See the job summary for details.",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
