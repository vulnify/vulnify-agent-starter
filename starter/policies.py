"""Load the starter policies and evaluate them offline.

This is the decision the mock server returns. It is not the Vulnify risk engine.
ALLOW overrides, and BLOCK wins over REVIEW and ALLOW when more than one rule matches.
Resource types other than ANY are rejected: the mock does not know how a resource
name is classified. Apply the file in Vulnify for that.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

FAMILY = {
    "READ_DATA": "READ",
    "WRITE_DATA": "WRITE",
    "DELETE_DATA": "DELETE",
    "EXPORT_DATA": "EXPORT",
    "SEND_EMAIL": "SEND_EMAIL",
}
EXTERNAL = {"EXTERNAL_EMAIL", "EXTERNAL_API"}
SUPPORTED_CONDITIONS = {"action", "destination", "minRecords", "maxRecords"}
RANK = {"ALLOW": 1, "REVIEW": 2, "BLOCK": 3}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def policy_dir() -> Path:
    return repo_root() / "vulnify" / "policies"


def test_dir() -> Path:
    return repo_root() / "vulnify" / "tests"


def load_documents(directory: Path) -> List[Dict[str, Any]]:
    files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
    if not files:
        raise FileNotFoundError(f"No policy YAML in {directory}")
    docs: List[Dict[str, Any]] = []
    for path in files:
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if doc is not None:
                docs.append(doc)
    return docs


def load_policies(directory: Optional[Path] = None) -> List[Dict[str, Any]]:
    docs = [doc for doc in load_documents(directory or policy_dir()) if doc.get("kind") == "Policy"]
    if not docs:
        raise FileNotFoundError("No kind: Policy documents found")
    for doc in docs:
        _require_supported(doc)
    return docs


def load_cases(directory: Optional[Path] = None) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for doc in load_documents(directory or test_dir()):
        if doc.get("kind") != "PolicyTest":
            continue
        for case in doc.get("cases") or []:
            cases.append(case)
    return cases


def decide(event: Dict[str, Any], policies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the winning starter policy, or ALLOW when none match."""
    action = event.get("action") or ""
    if action not in FAMILY:
        raise ValueError(f"Unknown action {action}")
    matched = [policy for policy in policies if _matches(policy, event)]
    if not matched:
        return {"decision": "ALLOW", "reasons": ["No starter policy matched"], "policy": None}
    winner = max(matched, key=lambda policy: RANK[policy["spec"]["decision"]])
    name = winner["metadata"]["name"]
    description = winner["spec"].get("description") or name
    return {
        "decision": winner["spec"]["decision"],
        "reasons": [description, f"Policy matched: {name}"],
        "policy": name,
    }


def to_api(result: Dict[str, Any], event_id: str) -> Dict[str, Any]:
    decision = result["decision"]
    body: Dict[str, Any] = {
        "id": event_id,
        "decision": decision,
        "finalDecision": decision,
        "evaluatedDecision": decision,
        "reasons": list(result["reasons"]),
        "sandbox": True,
        "monitored": False,
        "degraded": False,
    }
    if result.get("policy"):
        body["policy"] = {"name": result["policy"]}
    if decision == "REVIEW":
        body["review"] = {"status": "PENDING"}
    return body


def _require_supported(doc: Dict[str, Any]) -> None:
    name = (doc.get("metadata") or {}).get("name") or "(unnamed)"
    spec = doc.get("spec") or {}
    resource = spec.get("resource") or "ANY"
    if resource != "ANY":
        raise ValueError(
            f"Policy {name} uses resource type {resource}. "
            "The offline mock only evaluates resource ANY. Apply the file in Vulnify to use resource types."
        )
    unknown = set((spec.get("condition") or {})) - SUPPORTED_CONDITIONS
    if unknown:
        fields = ", ".join(sorted(unknown))
        raise ValueError(
            f"Policy {name} uses condition fields the offline mock does not evaluate: {fields}. "
            "Apply the file in Vulnify to use them."
        )


def _matches(policy: Dict[str, Any], event: Dict[str, Any]) -> bool:
    spec = policy["spec"]
    if spec.get("enabled", True) is False:
        return False
    if spec.get("mode", "ENFORCE") != "ENFORCE":
        return False
    family = FAMILY[event["action"]]
    wanted = spec["action"]
    if wanted != "ANY" and wanted != family:
        return False
    condition = spec.get("condition") or {}
    if "action" in condition and condition["action"] not in (event["action"], family):
        return False
    if "destination" in condition and not _destination_ok(condition["destination"], event.get("destination")):
        return False
    records = event.get("recordsAffected")
    below_min = "minRecords" in condition and (records is None or records < condition["minRecords"])
    above_max = "maxRecords" in condition and (records is None or records > condition["maxRecords"])
    return not below_min and not above_max


def _destination_ok(wanted: str, actual: Optional[str]) -> bool:
    if wanted == "EXTERNAL":
        return actual in EXTERNAL
    if wanted == "INTERNAL":
        return actual == "INTERNAL"
    return False
