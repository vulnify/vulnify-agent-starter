"""Scripted agent. Three tool calls, each one checked before it runs.

Swap the plan for your own model's tool calls. The check stays the same.
"""
import argparse
import os
import sys
from typing import Optional

from vulnify import Decision, Vulnify, VulnifyError

from starter.guarded import GuardedToolbox, ToolResult, ToolSpec
from starter.mock_api import start_mock, stop_mock
from starter.tools import delete_table, export_report, read_ticket

TOOLS = {
    "read_ticket": ToolSpec(read_ticket, action="READ_DATA", resource="Support Tickets"),
    "export_report": ToolSpec(
        export_report,
        action="EXPORT_DATA",
        resource="Sales Reports",
        destination="EXTERNAL_EMAIL",
    ),
    "delete_table": ToolSpec(
        delete_table,
        action="DELETE_DATA",
        resource="Production Database",
        records_affected=10000,
    ),
}

PLAN = [
    ("read_ticket", {"ticket_id": "T-1042"}),
    ("export_report", {"to": "partner@example.com", "records": 800}),
    ("delete_table", {"table": "customers"}),
]

MOCK_KEY = "vln_test_mock"


def load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key:
                os.environ.setdefault(key, value)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Run three tool calls through Vulnify before they execute.")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Evaluate vulnify/policies locally. No API key and no network.",
    )
    parser.add_argument(
        "--approve-review",
        action="store_true",
        help="With --mock, approve the REVIEW locally so that tool runs.",
    )
    args = parser.parse_args(argv)
    load_env()
    mock = args.mock or _truthy(os.environ.get("VULNIFY_MOCK", ""))
    if args.approve_review and not mock:
        print("--approve-review only applies to --mock. Approve a real REVIEW in Vulnify or in Slack.")
        return 2

    server = None
    try:
        if mock:
            server, base_url = start_mock(approve_reviews=args.approve_review)
            client = Vulnify(api_key=MOCK_KEY, base_url=base_url, fail_mode="closed", retries=0)
            timeout = 5.0 if args.approve_review else 0.0
            print("Mock mode: decisions come from vulnify/policies. No request is sent to api.vulnify.io.")
        else:
            key = os.environ.get("VULNIFY_API_KEY", "")
            if _missing_key(key):
                print("Sign up at https://app.vulnify.io and create a TEST key.")
                print("Put it in .env as VULNIFY_API_KEY. .env is gitignored. Copy .env.example.")
                print("Or run: python -m starter.main --mock")
                return 1
            if key.startswith("vln_live_"):
                print(
                    "Warning: this key is LIVE, so these decisions are recorded outside the sandbox. "
                    "A TEST key (vln_test_...) is the one to use while trying the starter.",
                    file=sys.stderr,
                )
            timeout = _timeout()
            client = Vulnify(api_key=key, fail_mode="closed")
            print("Using the Vulnify API. A TEST key stays in the sandbox.")

        def on_review(decision: Decision) -> None:
            if mock:
                print("   REVIEW. Resolving it in the local mock.")
            else:
                print(f"   REVIEW event {decision.id}.")
                print(f"   Approve it in Vulnify or in Slack. Waiting {timeout:.0f}s.")
            sys.stdout.flush()

        box = GuardedToolbox(
            client,
            agent=os.environ.get("VULNIFY_AGENT", "StarterAgent"),
            tools=TOOLS,
            review_timeout=timeout,
            on_review=on_review if timeout > 0 else None,
        )
        for name, call_args in PLAN:
            print(f"-> {name}({_format_args(call_args)})")
            try:
                result = box.call(name, **call_args)
            except VulnifyError as err:
                print(f"   {err}")
                return 1
            print(_format_result(result, mock=mock, timeout=timeout))
            hint = _hint(name, result, mock=mock)
            if hint:
                print(hint)
        return 0
    finally:
        stop_mock(server)


def _format_args(args: dict) -> str:
    return ", ".join(f"{key}={value!r}" for key, value in args.items())


def _format_result(result: ToolResult, mock: bool, timeout: float) -> str:
    approved = result.reviewed and result.ran
    head = "REVIEW approved, now ALLOW" if approved else result.decision
    if result.policy:
        head += f"  policy {result.policy}"
    lines = [f"   {head}"]
    if result.reasons:
        lines.append("   " + "; ".join(result.reasons))
    if result.degraded:
        lines.append("   Vulnify could not be reached. The tool did not run.")
    elif result.ran:
        lines.append(f"   ran: {result.output}")
    else:
        lines.append("   not run")
    if result.decision == "REVIEW" and not result.ran:
        lines.append("   Held for a person to approve in Vulnify or in Slack.")
        if mock:
            lines.append("   Re-run with --approve-review to let the mock approve it.")
        elif result.event_id:
            lines.append(f"   event {result.event_id}")
            if timeout <= 0:
                lines.append("   Set VULNIFY_REVIEW_TIMEOUT above 0 to wait in this process.")
    return "\n".join(lines)


def _hint(name: str, result: ToolResult, mock: bool) -> str:
    if mock or result.degraded:
        return ""
    if name == "delete_table" and result.decision == "ALLOW":
        return (
            "   block-production-deletes is not in this workspace yet, so the delete was allowed.\n"
            "   Apply vulnify/policies with an org-wide LIVE key, or run: python -m starter.main --mock"
        )
    if name == "export_report" and result.decision == "BLOCK":
        return (
            "   A REVIEW policy cannot loosen a risk-engine BLOCK. "
            "Classify Sales Reports as Internal if this export should wait for a person."
        )
    return ""


def _missing_key(key: str) -> bool:
    return (not key) or key.endswith("replace_me")


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _timeout() -> float:
    raw = os.environ.get("VULNIFY_REVIEW_TIMEOUT", "0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        print("VULNIFY_REVIEW_TIMEOUT must be a number of seconds. Using 0.")
        return 0.0


if __name__ == "__main__":
    sys.exit(main())
