#!/usr/bin/env python3
"""Run fresh Lab 3 probes; the official copy comes from the canonical bundle."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid


GROUPS = {
    "a1": ("frr", ("bgp4", "bgp6")),
    "a2": ("frr", ("frr4", "frr6")),
    "a3": ("frr", ("vxlan",)),
    "b0": ("ovs", ()),
    "b1": ("ovs", ("intra4", "intra6")),
    "b2": ("ovs", ("inter4", "inter6")),
    "b3": ("ovs", ("transit4", "transit6", "vxlan")),
    "b4": ("ovs", ("fib-sync",)),
    "b5": ("ovs", ("ttl4", "ttl6")),
    "b6": ("ovs", ("withdrawal",)),
    "b7": ("ovs", ("failover",)),
    "b8": ("ovs", ("policy",)),
    "b9": ("ovs", ("new-as",)),
    "b10": ("ovs", ("control-down",)),
}
REPORT_CASES = (
    "frr-bgp4", "frr-bgp6", "frr-vxlan",
    "ovs-transit4", "ovs-transit6", "ovs-ttl4", "ovs-ttl6",
    "ovs-withdrawal", "ovs-failover", "ovs-control-down",
)
REPORT_SECTIONS = (
    "Topology and addressing",
    "Control and data planes",
    "Prefix matching and route lifecycle",
    "L2 versus L3 hop behavior",
    "Failure and recovery",
    "VXLAN and MTU",
    "Limitations",
)
EVIDENCE_START = "<!-- BEGIN EVIDENCE -->"
EVIDENCE_END = "<!-- END EVIDENCE -->"


def execute(arguments, timeout):
    container = os.environ.get("CONTAINER", "lab3")
    return subprocess.run(
        ["docker", "exec", container, "python3", "harness/lab3.py", *arguments],
        capture_output=True, text=True, timeout=timeout,
    )


def probe_document(case, output):
    document = json.loads(output)
    if not isinstance(document, dict) or document.get("case") != case:
        raise ValueError(f"{case}: wrong or missing case identity")
    if type(document.get("passed")) is not bool:
        raise ValueError(f"{case}: 'passed' must be a JSON boolean")
    if not isinstance(document.get("measurements"), dict):
        raise ValueError(f"{case}: measurements must be an object")
    errors = document.get("errors")
    if not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
        raise ValueError(f"{case}: errors must be a list of strings")
    if document["passed"] and (errors or not document["measurements"]):
        raise ValueError(f"{case}: a pass needs actual measurements and no errors")
    return document


def save_probe(root, plane, case, document, exit_code):
    directory = root / "results"
    directory.mkdir(exist_ok=True)
    document = dict(document, validation_plane=plane, validation_run=uuid.uuid4().hex,
                    validation_exit_code=exit_code)
    path = directory / f"{plane}-{case}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def run_group(group, root, run=execute):
    plane, cases = GROUPS[group]
    print(f"=== Lab 3 {group}: {plane} data plane ===", flush=True)
    for name in ("results", "captures"):
        directory = root / name
        if directory.is_symlink():
            raise ValueError(f"evidence directory must not be a symlink: {directory}")
        directory.mkdir(exist_ok=True)
    for case in cases:
        path = root / "results" / f"{plane}-{case}.json"
        if path.exists():
            path.unlink()
    process = run(["deploy", "--plane", plane], 150)
    if process.stdout.strip():
        print(process.stdout.rstrip())
    if process.stderr:
        print(process.stderr.rstrip(), file=sys.stderr)
    if process.returncode:
        print(f"FAIL: {plane} deployment exited {process.returncode}; read the original error.", file=sys.stderr)
        return False
    if not cases:
        status = run(["status", "--json"], 30)
        if status.returncode:
            print(status.stderr, file=sys.stderr)
            return False
        document = json.loads(status.stdout)
        if not isinstance(document, dict) or not document:
            raise ValueError("deployment status must be a nonempty JSON object")
        print(json.dumps(document, indent=2))
        print("PASS: OVS virtual router deployed")
        return True
    passed = True
    for case in cases:
        process = run(["check", case, "--json"], 150)
        if process.stderr:
            print(process.stderr.rstrip(), file=sys.stderr)
        document = probe_document(case, process.stdout)
        path = save_probe(root, plane, case, document, process.returncode)
        actual = process.returncode == 0 and document["passed"] and not document["errors"]
        passed = passed and actual
        print(f"{'PASS' if actual else 'FAIL'}: {plane}/{case}; evidence {path.relative_to(root)}")
        print(json.dumps(document["measurements"], sort_keys=True))
        for error in document["errors"]:
            print(f"      {error}", file=sys.stderr)
        if process.returncode and document["passed"]:
            print(f"      check claimed success but exited {process.returncode}", file=sys.stderr)
    return passed


def evidence_summary(root):
    """Summarise this checkout's latest probe records for the report block.

    A missing, stale or failed record is listed as passed=false; it never makes
    this command fail.  The report check only verifies the block's shape, so a
    failed probe costs its own points, never the report's."""
    summary = {}
    for name in REPORT_CASES:
        plane, case = name.split("-", 1)
        path = root / "results" / f"{name}.json"
        passed = False
        if path.is_file() and not path.is_symlink():
            try:
                document = probe_document(case, path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                document = None
            passed = bool(
                document is not None and document["passed"]
                and document.get("validation_plane") == plane
                and document.get("validation_exit_code") == 0
                and re.fullmatch(r"[0-9a-f]{32}", str(document.get("validation_run", ""))))
        summary[name] = {"plane": plane, "passed": passed}
    return summary


def section_body(text, heading):
    match = re.search(rf"(?m)^## {re.escape(heading)}\s*$", text)
    if not match:
        raise ValueError(f"REPORT.md is missing '## {heading}'")
    following = text[match.end():]
    return re.split(r"(?m)^## ", following, maxsplit=1)[0].strip()


MINIMUM_OWN_TEXT = 80
# ai-usage.md: only the student's own section counts.  AI assistants append to
# the "## Assistant log" table after it (see AGENTS.md); that log is not counted.
AI_VERIFICATION_HEADING = "My verification"


def own_text(text):
    """Text the student wrote: HTML comments, headings and the template's own
    instruction lines (lines starting with 'TODO:') are not counted. Words such
    as 'todo' or 'placeholder' inside your own sentences are fine."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    kept = [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith(("#", "TODO:"))]
    return "\n".join(kept)


def check_evidence(text):
    """Check the shape of the report's evidence block, not the run's outcome."""
    if text.count(EVIDENCE_START) != 1 or text.count(EVIDENCE_END) != 1:
        raise ValueError(f"REPORT.md must keep exactly one {EVIDENCE_START} ... {EVIDENCE_END} block")
    block = text.split(EVIDENCE_START, 1)[1].split(EVIDENCE_END, 1)[0].strip()
    fenced = re.fullmatch(r"```json\s*\n(.*?)\n```", block, re.S)
    if fenced:
        block = fenced.group(1)
    hint = "paste the output of `python3 tests/grade.py evidence` after your latest runs"
    try:
        observed = json.loads(block)
    except json.JSONDecodeError as exc:
        raise ValueError(f"the evidence block is not valid JSON ({exc}); {hint}") from exc
    planes = {name: name.split("-", 1)[0] for name in REPORT_CASES}
    if not isinstance(observed, dict) or set(observed) != set(planes):
        raise ValueError(f"the evidence block must list exactly these cases: "
                         f"{', '.join(REPORT_CASES)}; {hint}")
    for name in REPORT_CASES:
        claim = observed[name]
        if (not isinstance(claim, dict) or set(claim) != {"plane", "passed"}
                or claim["plane"] != planes[name] or type(claim["passed"]) is not bool):
            raise ValueError(f'evidence claim "{name}" must be '
                             f'{{"plane": "{planes[name]}", "passed": true or false}}; {hint}')


def grade_report(root):
    text = (root / "REPORT.md").read_text(encoding="utf-8")
    if "<!-- BEGIN" + " KEY -->" in text:
        raise ValueError("materialize the private key before validating its report")
    problems = []
    try:
        check_evidence(text)
    except ValueError as exc:
        problems.append(str(exc))
    for heading in REPORT_SECTIONS:
        try:
            body = own_text(section_body(text, heading))
        except ValueError as exc:
            problems.append(f"{exc}; keep all seven headings")
            continue
        if len(body) < MINIMUM_OWN_TEXT:
            problems.append(f"'## {heading}' has {len(body)} characters of your own text; "
                            f"write at least {MINIMUM_OWN_TEXT} (the template's 'TODO:' line does not count)")
    usage = (root / "ai-usage.md").read_text(encoding="utf-8")
    try:
        disclosure = own_text(section_body(usage, AI_VERIFICATION_HEADING))
    except ValueError:
        problems.append(f"ai-usage.md is missing '## {AI_VERIFICATION_HEADING}'; keep the template's "
                        "headings and write your verification under it")
    else:
        if len(disclosure) < MINIMUM_OWN_TEXT:
            problems.append(f"ai-usage.md '## {AI_VERIFICATION_HEADING}' has {len(disclosure)} characters of "
                            f"your own text; write at least {MINIMUM_OWN_TEXT} (the template's 'TODO:' line "
                            "and the '## Assistant log' table do not count). Using no AI is valid: say so "
                            "and describe how you verified your work")
    if problems:
        raise ValueError("the report check found " + str(len(problems)) + " problem(s):\n  - "
                         + "\n  - ".join(problems))
    print("PASS: report sections, evidence block and AI disclosure are present")
    print("INFO: the TA assesses correctness of the explanations, not this length check")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", choices=[*GROUPS, "report", "evidence"])
    arguments = parser.parse_args()
    root = Path.cwd()
    try:
        if arguments.group == "evidence":
            print(json.dumps(evidence_summary(root), indent=2, sort_keys=True))
            return 0
        passed = grade_report(root) if arguments.group == "report" else run_group(arguments.group, root)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        if arguments.group == "report" and isinstance(exc, ValueError):
            print(f"FAIL: {exc}", file=sys.stderr)
        else:
            print(f"FAIL: Lab 3 check could not complete: {exc}", file=sys.stderr)
        return 1
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
