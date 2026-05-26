from pydantic import BaseModel
from uuid import UUID
from typing import List


class CanonicalGoal(BaseModel):
    """
    Injected into every agent prompt to prevent goal drift.
    AI Builder's Handbook Cap 15 §15.5 — "drift from goal" failure mode.
    """
    workflow_id: UUID
    goal_statement: str   # 1-2 sentences, unambiguous
    success_criteria: List[str]  # binary checklist
    out_of_scope: List[str]  # what is NOT part of the goal

    def as_context_block(self) -> str:
        """Returns formatted XML block for injection into agent prompts."""
        criteria = "\n".join(f"- {c}" for c in self.success_criteria)
        out_of = "\n".join(f"- {o}" for o in self.out_of_scope)
        return f"""<canonical_goal>
Goal: {self.goal_statement}
Success criteria:
{criteria}
Out of scope:
{out_of}
</canonical_goal>"""
