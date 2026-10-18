"""A scripted 'agent' that makes three tool calls. Swap the plan for your LLM's tool calls."""
import os
import sys

from vulnify import Vulnify

from starter.guarded import GuardedToolbox, ToolSpec
from starter.tools import delete_table, export_customers, read_ticket

TOOLS = {
    "read_ticket": ToolSpec(read_ticket, action="READ_DATA", resource="Support Tickets"),
    "export_customers": ToolSpec(export_customers, action="EXPORT_DATA", resource="Customer Database",
                                 destination="EXTERNAL_EMAIL"),
    "delete_table": ToolSpec(delete_table, action="DELETE_DATA", resource="Customer Database"),
}

PLAN = [
    ("read_ticket", {"ticket_id": "T-1042"}),                                    # usually ALLOW
    ("export_customers", {"to": "partner@example.com", "records": 800}),       # usually REVIEW
    ("delete_table", {"table": "customers"}),                                    # BLOCK with a block policy
]


def load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    load_env()
    key = os.environ.get("VULNIFY_API_KEY", "")
    if not key or key.endswith("replace_me"):
        print("Set VULNIFY_API_KEY in .env (copy .env.example). Get a key at https://app.vulnify.io")
        return 1
    client = Vulnify(api_key=key, fail_mode="closed")
    box = GuardedToolbox(client, agent="StarterAgent", tools=TOOLS,
                         review_timeout=float(os.environ.get("VULNIFY_REVIEW_TIMEOUT", "300")))
    for name, args in PLAN:
        print(f"-> {name}({args})")
        print("   ", box.call(name, **args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
