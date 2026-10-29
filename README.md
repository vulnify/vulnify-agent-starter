# Vulnify agent starter

A small Python agent whose tool calls go through [Vulnify](https://www.vulnify.io/?utm_source=github&utm_medium=template&utm_campaign=starter) before they run. Vulnify answers **ALLOW**, **REVIEW**, or **BLOCK** in real time, and every decision lands in the audit trail.

| Decision | What happens |
|---|---|
| **ALLOW** | the tool runs |
| **REVIEW** | the tool waits until a person approves or denies it, in Vulnify or in Slack |
| **BLOCK** | the tool does not run, and the agent gets the reasons |

If Vulnify cannot be reached, the call does not run (`fail_mode="closed"`).

## Quickstart

1. Sign up at [https://app.vulnify.io](https://app.vulnify.io/login?mode=register&utm_source=github&utm_medium=template&utm_campaign=starter).
2. Create a **TEST** key under [API keys](https://app.vulnify.io/api-keys). It starts with `vln_test_`.
3. Run:

```bash
git clone https://github.com/vulnify/vulnify-agent-starter.git
cd vulnify-agent-starter
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # paste the TEST key as VULNIFY_API_KEY
python -m starter.main
```

`.env` is gitignored. Do not commit the key.

The script makes three calls:

| Tool | What Vulnify is asked | With the policies in this repo |
|---|---|---|
| `read_ticket` | `READ_DATA` on Support Tickets | **ALLOW** |
| `export_report` | `EXPORT_DATA` of 800 records to an external email | **REVIEW** |
| `delete_table` | `DELETE_DATA` on Production Database | **BLOCK** |

`VULNIFY_REVIEW_TIMEOUT` defaults to `0`, so a REVIEW is printed and the script moves on. Set it above `0` to wait in this process while someone approves in Vulnify or in Slack.

On a fresh workspace, before those policies are applied, a read is allowed and a bulk external export is held for review. A delete is blocked once `block-production-deletes` is in the workspace. Until then the script says so. Apply the files with an org-wide LIVE key (below), or create the same three rules under Policies in the app.

A new agent name registers on first use and counts toward your plan's agent limit. The demo agent is `StarterAgent` (`VULNIFY_AGENT` overrides it). The resource names are `Support Tickets`, `Sales Reports`, and `Production Database`.

### No key yet

```bash
python -m starter.main --mock
```

Mock mode runs the same `Vulnify` client against a local server that evaluates `vulnify/policies`. Nothing is sent to `api.vulnify.io`. You should see ALLOW, then REVIEW, then BLOCK:

```
Mock mode: decisions come from vulnify/policies. No request is sent to api.vulnify.io.
-> read_ticket(ticket_id='T-1042')
   ALLOW  policy allow-reads
   Reads are allowed.; Policy matched: allow-reads
   ran: Ticket T-1042: customer asks for their invoice history.
-> export_report(to='partner@example.com', records=800)
   REVIEW  policy review-bulk-external-export
   An export of 100 or more records to an external destination waits for a person.; Policy matched: review-bulk-external-export
   not run
   Held for a person to approve in Vulnify or in Slack.
-> delete_table(table='customers')
   BLOCK  policy block-production-deletes
   Deletes are blocked, including destructive actions on production data.; Policy matched: block-production-deletes
   not run
```

`--approve-review` approves that REVIEW inside the mock and lets the export run. A real REVIEW is approved in Vulnify or in Slack, not by that flag.

Mock mode follows the files in this repo. It does not score with the risk engine. An export of data classified Customer PII or Sensitive to an external destination is blocked by the risk engine, and a REVIEW policy cannot loosen that. Keep `Sales Reports` classified Internal if that export should wait for a person.

## Policies

`vulnify/policies/starter.yaml`:

| Policy | Rule |
|---|---|
| `allow-reads` | reads are allowed |
| `review-bulk-external-export` | an export of 100 or more records to an external email or API waits for a person |
| `block-production-deletes` | deletes are blocked, including destructive actions on production data |

`spec.resource` is a resource type. `ANY` matches every type, so the delete rule blocks every delete, not only a resource whose name contains "production". Narrow it in the app if some deletes should go through.

Check the files offline, with no key:

```bash
pip install "vulnify[cli]==0.4.2"
vulnify policies validate
```

With any non-revoked key, including a TEST key, evaluate them without writing an event:

```bash
vulnify test --local
```

Apply them to the workspace. This needs an org-wide **LIVE** key (`vln_live_...`, not bound to one agent). A TEST key cannot apply.

```bash
vulnify policies apply --dry-run
vulnify policies apply
```

Policy files: https://docs.vulnify.io/cli/policy-files/  
CLI: https://docs.vulnify.io/cli/

## Use with

Runnable examples live in [vulnify-examples](https://github.com/vulnify/vulnify-examples). This repo does not copy them.

### LangChain and LangGraph

[langgraph/](https://github.com/vulnify/vulnify-examples/tree/main/langgraph) asks Vulnify, then branches on ALLOW, REVIEW, and BLOCK. `guard_langchain_tool` and `langgraph_tool_guard` are in `vulnify` 0.4.2. [Adapters](https://docs.vulnify.io/sdks/adapters/).

### CrewAI

[crewai/](https://github.com/vulnify/vulnify-examples/tree/main/crewai). `guard_crewai_tool` is in `vulnify` 0.4.2.

### Vercel AI SDK

[vercel-ai-sdk/](https://github.com/vulnify/vulnify-examples/tree/main/vercel-ai-sdk). `guardAiSdkTools` is in `@vulnify/sdk` 0.3.3.

### OpenAI Agents SDK

[openai-agents-sdk/](https://github.com/vulnify/vulnify-examples/tree/main/openai-agents-sdk). `guard_openai_agents_tool` is in `vulnify` 0.4.2.

### Claude Code hooks

[claude-code-hook/](https://github.com/vulnify/vulnify-examples/tree/main/claude-code-hook). A PreToolUse hook checks a shell command, file write, fetch, or MCP tool call before Claude Code runs it.

Using Claude without this repo: Vulnify is in Claude's connector directory. [Connect to Claude](https://claude.ai/directory/vulnify), sign in, then follow the [Claude connector guide](https://docs.vulnify.io/guides/claude-connector-approval/?utm_source=github&utm_medium=template&utm_campaign=starter).

SDK reference: [Python](https://docs.vulnify.io/sdks/python/) (`vulnify` 0.4.2) and [Node.js](https://docs.vulnify.io/sdks/node/) (`@vulnify/sdk` 0.3.3).

## Use it on your own tool

```python
import os

from vulnify import Vulnify

from starter.guarded import GuardedToolbox, ToolSpec

box = GuardedToolbox(
    Vulnify(api_key=os.environ["VULNIFY_API_KEY"], fail_mode="closed"),
    agent="BillingBot",
    tools={
        "send_invoice": ToolSpec(
            send_invoice,
            action="SEND_EMAIL",
            resource="Invoices",
            destination="EXTERNAL_EMAIL",
        )
    },
)
print(box.call("send_invoice", customer_id="c_42"))
```

`check()` is the same decision without running the tool. `guard()` runs a callable only when the effective decision is ALLOW.

## Tests

GitHub Actions are not required. From a checkout:

```bash
pip install -e ".[dev]"
ruff check .
python -m unittest discover -s tests -t . -v
```

The tests use a local fake of the decision API. No key, and no call to `api.vulnify.io`.
