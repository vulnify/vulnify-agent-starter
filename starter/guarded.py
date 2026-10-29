"""Every tool call goes through Vulnify before it executes.

ALLOW  -> the tool runs.
REVIEW -> the tool waits when a timeout is set, otherwise it does not run.
BLOCK  -> the tool does not run, and the caller gets the reasons.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from vulnify import Decision, Vulnify


@dataclass
class ToolSpec:
    fn: Callable[..., str]
    action: str
    resource: str
    destination: Optional[str] = None
    records_affected: Optional[int] = None


@dataclass
class ToolResult:
    decision: str
    ran: bool
    output: str
    policy: Optional[str] = None
    reasons: Tuple[str, ...] = ()
    event_id: Optional[str] = None
    reviewed: bool = False
    degraded: bool = False

    def __str__(self) -> str:
        if self.ran:
            return f"ALLOW: {self.output}"
        why = "; ".join(self.reasons) if self.reasons else self.output
        return f"{self.decision}: {why}"


class GuardedToolbox:
    def __init__(
        self,
        client: Vulnify,
        agent: str,
        tools: Dict[str, ToolSpec],
        review_timeout: float = 0,
        on_review: Optional[Callable[[Decision], None]] = None,
    ):
        self.client = client
        self.agent = agent
        self.tools = tools
        self.review_timeout = review_timeout
        self.on_review = on_review

    def call(self, name: str, records: Optional[int] = None, **kwargs: Any) -> ToolResult:
        spec = self.tools[name]
        records_affected = records if records is not None else spec.records_affected
        tool_kwargs = dict(kwargs)
        if records is not None:
            tool_kwargs["records"] = records
        decision = self.client.check(
            agent=self.agent,
            action=spec.action,
            resource=spec.resource,
            destination=spec.destination,
            records_affected=records_affected,
        )
        effective = decision.final_decision if decision.final_decision is not None else decision.decision
        reviewed = False
        if effective == "REVIEW" and self.review_timeout > 0 and decision.id:
            if self.on_review is not None:
                self.on_review(decision)
            outcome = self.client.wait_for_review(decision.id, timeout=self.review_timeout)
            reviewed = True
            if outcome in ("ALLOW", "APPROVED"):
                effective = "ALLOW"
            else:
                # Denial and expiry must not run the tool. A timeout is still a pending REVIEW.
                reasons = tuple(decision.reasons) + (f"Review {outcome.lower()}",)
                label = "REVIEW" if outcome == "TIMEOUT" else "BLOCK"
                return _result(decision, False, "", reasons=reasons, reviewed=True, label=label)
        if effective == "ALLOW":
            return _result(decision, True, spec.fn(**tool_kwargs), reviewed=reviewed)
        return _result(decision, False, "", reviewed=reviewed)


def _result(
    decision: Decision,
    ran: bool,
    output: str,
    reasons: Optional[Tuple[str, ...]] = None,
    reviewed: bool = False,
    label: Optional[str] = None,
) -> ToolResult:
    policy = None
    if isinstance(decision.policy, dict):
        policy = decision.policy.get("name")
    stored = decision.final_decision if decision.final_decision is not None else decision.decision
    # After an approval the stored decision is still REVIEW and final_decision is ALLOW.
    shown = label or ("ALLOW" if ran else stored)
    return ToolResult(
        decision=shown,
        ran=ran,
        output=output,
        policy=policy,
        reasons=tuple(decision.reasons) if reasons is None else reasons,
        event_id=decision.id,
        reviewed=reviewed,
        degraded=bool(decision.degraded),
    )
