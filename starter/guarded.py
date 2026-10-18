"""Every tool call goes through Vulnify before it executes.

ALLOW  -> the tool runs.
REVIEW -> the agent waits for a human to approve or deny (in Vulnify or Slack).
BLOCK  -> the tool is refused and the agent is told why.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from vulnify import Vulnify, VulnifyBlockedError


@dataclass
class ToolSpec:
    fn: Callable[..., str]
    action: str
    resource: str
    destination: Optional[str] = None


class GuardedToolbox:
    def __init__(self, client: Vulnify, agent: str, tools: Dict[str, ToolSpec], review_timeout: float = 300):
        self.client = client
        self.agent = agent
        self.tools = tools
        self.review_timeout = review_timeout

    def call(self, name: str, records: Optional[int] = None, **kwargs: Any) -> str:
        spec = self.tools[name]
        if records is not None:
            kwargs["records"] = records
        try:
            return self.client.guard(
                lambda: spec.fn(**kwargs),
                wait={"timeout": self.review_timeout},
                agent=self.agent,
                action=spec.action,
                resource=spec.resource,
                destination=spec.destination,
                records_affected=records,
            )
        except VulnifyBlockedError as err:
            return f"REFUSED by Vulnify: {err}"
