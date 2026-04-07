from typing import Any, Dict

from openenv.core.client_types import StepResult
from openenv.core.env_client import EnvClient

from .models import (
    AccessibilityAuditAction,
    AccessibilityAuditObservation,
    AccessibilityAuditState,
)


class AccessibilityAuditEnv(
    EnvClient[
        AccessibilityAuditAction,
        AccessibilityAuditObservation,
        AccessibilityAuditState,
    ]
):
    """Client for the Accessibility Audit environment."""

    async def connect(self) -> "AccessibilityAuditEnv":
        from websockets.asyncio.client import connect as ws_connect

        self._ws = await ws_connect(
            self._ws_url,
            open_timeout=self._connect_timeout,
            max_size=self._max_message_size,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=300,
        )
        return self

    def _step_payload(self, action: AccessibilityAuditAction) -> Dict[str, Any]:
        return action.model_dump()

    def _parse_result(
        self, payload: Dict[str, Any]
    ) -> StepResult[AccessibilityAuditObservation]:
        obs_data = payload.get("observation", payload)
        obs = AccessibilityAuditObservation(**obs_data)
        return StepResult(
            observation=obs,
            reward=payload.get("reward", getattr(obs, "reward", None)),
            done=payload.get("done", getattr(obs, "done", False)),
        )

    def _parse_state(self, payload: Dict[str, Any]) -> AccessibilityAuditState:
        return AccessibilityAuditState(**payload)
