# Vulnify agent starter (Python)

A minimal agent whose tool calls are authorized by [Vulnify](https://www.vulnify.io/?utm_source=github&utm_medium=template&utm_campaign=starter) **before** they run:

| Decision | What the agent does |
|---|---|
| **ALLOW** | the tool runs |
| **REVIEW** | the agent waits while a human approves or denies it, in Vulnify or in Slack |
| **BLOCK** | the tool is refused and the agent gets the reasons |

Every decision lands in the Vulnify audit trail.

## Quickstart

1. **Create a free account:** https://app.vulnify.io/login?mode=register&utm_source=github&utm_medium=template&utm_campaign=starter
2. Create an API key in the dashboard (app.vulnify.io).
3. Run it:

```bash
git clone https://github.com/vulnify/vulnify-agent-starter.git && cd vulnify-agent-starter
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # paste your VULNIFY_API_KEY
python -m starter.main
```

The scripted agent makes three calls:

| Tool | Vulnify action | Typical decision |
|---|---|---|
| `read_ticket` | `READ_DATA` on Support Tickets | ALLOW |
| `export_customers` (800 records to an external email) | `EXPORT_DATA` → `EXTERNAL_EMAIL` | REVIEW (export operation, external destination, large data volume) |
| `delete_table` | `DELETE_DATA` on Customer Database | BLOCK if you have a policy that blocks deletes |

The actual outcome depends on the policies in your workspace. While the REVIEW waits, open the dashboard (or Slack, if connected) and approve or deny it.

**Using Claude?** You can try the same ALLOW / REVIEW / BLOCK flow without code: **[Connect to Claude](https://claude.ai/directory/vulnify)** (Vulnify is in Claude's connector directory), sign in, then follow the [Claude connector guide](https://docs.vulnify.io/guides/claude-connector-approval/?utm_source=github&utm_medium=template&utm_campaign=starter).

## Use it with your own agent

```python
from starter.guarded import GuardedToolbox, ToolSpec

tools = {"send_invoice": ToolSpec(send_invoice, action="SEND_EMAIL", resource="Invoices",
                                  destination="EXTERNAL_EMAIL")}
box = GuardedToolbox(Vulnify(api_key=...), agent="BillingBot", tools=tools)
box.call("send_invoice", customer_id="c_42")   # call this from your LLM's tool-call handler
```

`fail_mode="closed"` (the default) blocks if Vulnify can't be reached.

## Tests (offline, no key needed)

```bash
pip install -e '.[dev]'
ruff check . && python -m unittest discover -s tests -t . -v
```

Docs: https://docs.vulnify.io/sdks/python/
