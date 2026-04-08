"""Core environment: reset() / step() / state()."""
from __future__ import annotations

import asyncio
import os
from typing import Dict
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment

from ..models import (
    AccessibilityAuditAction,
    AccessibilityAuditObservation,
    AccessibilityAuditState,
)
from .grader import (
    AxeGrader,
    compute_reward,
    format_violations_summary,
    weighted_score,
)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "html_templates")

TASK_FILES: Dict[str, str] = {
    "easy": "easy_landing_page.html",
    "medium": "medium_dashboard.html",
    "hard": "hard_webapp.html",
    "expert": "expert_checkout.html",
}

TASK_DESCRIPTIONS: Dict[str, str] = {
    "easy": (
        "Easy: A marketing landing page with a small number of WCAG 2.1 "
        "violations. Fix every accessibility issue reported by axe-core "
        "while preserving the visual layout and copy."
    ),
    "medium": (
        "Medium: An analytics dashboard with several WCAG 2.1 violations "
        "across heading hierarchy, link text, color contrast, landmarks, "
        "and form structure. Fix all reported issues."
    ),
    "hard": (
        "Hard: A multi-component CRM web app with 15+ WCAG 2.1 violations "
        "spanning ARIA roles, modal dialogs, tab patterns, missing labels, "
        "missing alt text, language attribute, contrast, table headers, "
        "duplicate ids, and label-content-name mismatch. Fix every issue "
        "reported by axe-core."
    ),
    "expert": (
        "Expert: An e-commerce checkout flow with subtle WCAG 2.1 violations "
        "including autocomplete tokens on payment/address fields, "
        "label-content-name mismatch, low-contrast help links and "
        "placeholders, duplicate ids, ARIA spinbutton without accessible "
        "name, fieldset/legend on the payment radio group, table headers, "
        "and an icon-only cart link without an accessible name. Fix every "
        "issue reported by axe-core."
    ),
}


def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class AccessibilityAuditEnvironment(Environment):
    def __init__(self) -> None:
        self._state = AccessibilityAuditState(
            episode_id=str(uuid4()),
            step_count=0,
        )
        self._templates: Dict[str, str] = self._load_templates()
        self._grader = AxeGrader()

    # ------------------------------------------------------------------
    def _load_templates(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for task_id, fname in TASK_FILES.items():
            path = os.path.join(TEMPLATE_DIR, fname)
            with open(path, "r", encoding="utf-8") as f:
                out[task_id] = f.read()
        return out

    def _get_task_description(self, task_id: str) -> str:
        return TASK_DESCRIPTIONS.get(task_id, "Fix accessibility violations in the HTML.")

    # ------------------------------------------------------------------
    def reset(self, task_id: str = "easy") -> AccessibilityAuditObservation:
        if task_id not in self._templates:
            task_id = "easy"

        loop = _get_or_create_loop()
        loop.run_until_complete(self._grader.initialize())

        html = self._templates[task_id]

        self._state = AccessibilityAuditState(
            episode_id=str(uuid4()),
            step_count=0,
            task_id=task_id,
            original_html=html,
            current_html=html,
            max_steps=5,
        )

        violations = loop.run_until_complete(self._grader.run_audit(html))
        self._state.original_violations = violations
        self._state.original_weighted_score = weighted_score(violations)

        return AccessibilityAuditObservation(
            html_source=html,
            violations=violations,
            task_id=task_id,
            task_description=self._get_task_description(task_id),
            violation_count=len(violations),
            violation_summary=format_violations_summary(violations),
            done=False,
            reward=0.0,
        )

    # ------------------------------------------------------------------
    def step(self, action: AccessibilityAuditAction) -> AccessibilityAuditObservation:
        self._state.step_count += 1
        self._state.steps_taken = self._state.step_count
        self._state.current_html = action.fixed_html or ""

        loop = _get_or_create_loop()

        try:
            new_violations = loop.run_until_complete(
                self._grader.run_audit(action.fixed_html or "")
            )
        except Exception as exc:
            self._state.episode_complete = True
            return AccessibilityAuditObservation(
                html_source=action.fixed_html or "",
                violations=[],
                task_id=self._state.task_id,
                task_description=self._get_task_description(self._state.task_id),
                violation_count=0,
                violation_summary=f"Error processing HTML: {exc}",
                done=True,
                reward=1e-3,
            )

        reward = compute_reward(
            self._state.original_violations,
            new_violations,
            self._state.original_html,
            action.fixed_html or "",
        )

        done = (len(new_violations) == 0) or (
            self._state.step_count >= self._state.max_steps
        )
        self._state.episode_complete = done

        return AccessibilityAuditObservation(
            html_source=action.fixed_html or "",
            violations=new_violations,
            task_id=self._state.task_id,
            task_description=self._get_task_description(self._state.task_id),
            violation_count=len(new_violations),
            violation_summary=format_violations_summary(new_violations),
            done=done,
            reward=reward,
        )

    # ------------------------------------------------------------------
    @property
    def state(self) -> AccessibilityAuditState:
        return self._state
