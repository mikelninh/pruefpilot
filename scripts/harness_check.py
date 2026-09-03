from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path.cwd()
errors: list[str] = []

def fail(message: str) -> None:
    errors.append(message)

def read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

required = [
    "AGENTS.md",
    ".harness/project.json",
    ".harness/active-task.json",
    ".harness/HANDOFF.md",
    ".harness/receipts/README.md",
]
for item in required:
    if not (ROOT / item).exists():
        fail(f"missing required file {item}")

project = None
task = None
try:
    project = read_json(".harness/project.json")
except Exception as exc:
    fail(f"invalid .harness/project.json: {exc}")
try:
    task = read_json(".harness/active-task.json")
except Exception as exc:
    fail(f"invalid .harness/active-task.json: {exc}")

if project:
    if project.get("schema") != "mikel-harness-project-v0.1":
        fail("unsupported project schema")
    ident = project.get("project") or {}
    if not ident.get("name") or not ident.get("repository"):
        fail("project identity is incomplete")
    if len(project.get("sources_of_truth") or []) < 3:
        fail("sources_of_truth must map at least three areas")
    if not project.get("action_policy") or not project.get("retry_policy"):
        fail("action and retry policies are required")
    maximum = (project.get("retry_policy") or {}).get("max_retries")
    if not isinstance(maximum, int) or not 1 <= maximum <= 5:
        fail("project max_retries must be between 1 and 5")

if task and project:
    statuses = {"queued", "in_progress", "blocked", "ready_for_review", "completed", "abandoned"}
    if task.get("schema") != "mikel-harness-task-v0.1":
        fail("unsupported task schema")
    if not task.get("task_id") or not task.get("goal"):
        fail("task_id and goal are required")
    if task.get("status") not in statuses:
        fail(f"invalid task status {task.get('status')}")
    for key in ("sources", "outputs", "constraints", "done_when", "forbidden"):
        if not isinstance(task.get(key), list) or not task[key]:
            fail(f"{key} must be a non-empty array")
    risk = task.get("risk_class")
    if risk not in (project.get("action_policy") or {}):
        fail(f"unknown risk_class {risk}")
    if not isinstance(task.get("approval_required"), bool):
        fail("approval_required must be boolean")
    if risk in {"A3", "A4"} and task.get("approval_required") is not True:
        fail(f"{risk} tasks require human approval")
    maximum = project["retry_policy"]["max_retries"]
    retries = task.get("max_retries")
    if not isinstance(retries, int) or retries < 0 or retries > maximum:
        fail(f"task max_retries must be between 0 and {maximum}")
    if task.get("status") in {"ready_for_review", "completed"} and not task.get("evidence"):
        fail(f"{task.get('status')} tasks need evidence")
    for evidence in task.get("evidence") or []:
        if evidence.get("status") == "present" and evidence.get("path") and not (ROOT / evidence["path"]).exists():
            fail(f"evidence path does not exist: {evidence['path']}")
    if task.get("status") == "completed":
        receipt_path = task.get("receipt")
        if not receipt_path or not (ROOT / receipt_path).exists():
            fail("completed task must reference an existing receipt")
        else:
            try:
                receipt = read_json(receipt_path)
                if receipt.get("verdict") != "accepted":
                    fail("completed task receipt must have verdict=accepted")
            except Exception as exc:
                fail(f"invalid completion receipt: {exc}")

agents = ROOT / "AGENTS.md"
if agents.exists():
    text = agents.read_text(encoding="utf-8")
    if len(text.splitlines()) > 180:
        fail("AGENTS.md must remain under 180 lines")
    for phrase in ("Source-of-truth map", "Action classes", "Durable state", "Failure upgrades", "Definition of done"):
        if phrase not in text:
            fail(f"AGENTS.md missing section: {phrase}")

handoff = ROOT / ".harness/HANDOFF.md"
if handoff.exists():
    text = handoff.read_text(encoding="utf-8")
    for heading in ("## Status", "## Current step", "## Evidence", "## Open risks", "## Next owner"):
        if heading not in text:
            fail(f"HANDOFF.md missing heading: {heading}")

receipt_dir = ROOT / ((project or {}).get("receipt_dir") or ".harness/receipts")
if receipt_dir.exists():
    for file in receipt_dir.glob("*.json"):
        try:
            receipt = json.loads(file.read_text(encoding="utf-8"))
            for field in ("schema", "task_id", "verdict", "context_sources", "tools_used", "verification", "external_actions", "rollback_point", "next_owner"):
                if field not in receipt:
                    fail(f"{file.name} missing receipt field {field}")
            if receipt.get("verdict") not in {"accepted", "rejected", "partial"}:
                fail(f"{file.name} has invalid verdict {receipt.get('verdict')}")
            for action in receipt.get("external_actions") or []:
                if action.get("risk_class") in {"A3", "A4"} and action.get("approved") is not True:
                    fail(f"{file.name} contains an unapproved consequential external action")
        except Exception as exc:
            fail(f"invalid receipt {file.name}: {exc}")

if errors:
    for error in errors:
        print(f"HARNESS FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print(f"Harness OK: {project['project']['name']} / {task['task_id']} / {task['status']}")
