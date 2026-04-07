from typing import Any, Dict, List

from pydantic import Field

from openenv.core.env_server import Action, Observation, State


class AccessibilityAuditAction(Action):
    """Agent submits corrected HTML."""
    fixed_html: str = ""


class AccessibilityAuditObservation(Observation):
    """What the agent sees after reset/step."""
    html_source: str = ""
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    task_id: str = ""
    task_description: str = ""
    violation_count: int = 0
    violation_summary: str = ""


class AccessibilityAuditState(State):
    """Internal state tracking."""
    task_id: str = ""
    original_html: str = ""
    original_violations: List[Dict[str, Any]] = Field(default_factory=list)
    original_weighted_score: float = 0.0
    current_html: str = ""
    steps_taken: int = 0
    max_steps: int = 5
    episode_complete: bool = False