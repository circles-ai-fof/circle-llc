import contextlib
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)

DEFAULT_MAX_STEPS = 20
DEFAULT_COST_CAP_USD = 5.0
ALERT_THRESHOLD = 0.80  # R17: alert at 80% of cap


class TrajectoryBudgetExceededError(Exception):
    pass


@dataclass
class BudgetTracker:
    max_steps: int = DEFAULT_MAX_STEPS
    cost_cap_usd: float = DEFAULT_COST_CAP_USD
    steps_used: int = 0
    cost_used_usd: float = 0.0
    _alert_fired: bool = field(default=False, repr=False)

    def record_step(self, cost_usd: float = 0.0) -> None:
        self.steps_used += 1
        self.cost_used_usd += cost_usd

        # R17: alert at 80% of cost cap
        if not self._alert_fired and self.cost_used_usd >= self.cost_cap_usd * ALERT_THRESHOLD:
            logger.warning(
                "Cost alert (R17): %.2f USD used (%.0f%% of cap %.2f USD)",
                self.cost_used_usd, 100 * self.cost_used_usd / self.cost_cap_usd, self.cost_cap_usd,
            )
            self._alert_fired = True

        if self.steps_used > self.max_steps:
            raise TrajectoryBudgetExceededError(
                f"Step budget exceeded: {self.steps_used} > {self.max_steps}"
            )
        if self.cost_used_usd > self.cost_cap_usd:
            raise TrajectoryBudgetExceededError(
                f"Cost cap exceeded: ${self.cost_used_usd:.2f} > ${self.cost_cap_usd:.2f}"
            )


@contextlib.contextmanager
def trajectory_budget(max_steps: int = DEFAULT_MAX_STEPS, cost_cap_usd: float = DEFAULT_COST_CAP_USD):
    tracker = BudgetTracker(max_steps=max_steps, cost_cap_usd=cost_cap_usd)
    yield tracker
