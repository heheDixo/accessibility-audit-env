"""
axe-core grader with a persistent Chromium browser.

Launches the browser ONCE on first use and reuses it across step() calls.
Each audit creates and disposes only a new Page (~50ms) instead of a new
browser (~2s). Designed for the 2 vCPU / 8GB judging environment.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from playwright.async_api import Browser, async_playwright

# axe-core impact level → numeric weight used for the reward computation.
IMPACT_WEIGHTS: Dict[str, int] = {
    "critical": 4,
    "serious": 3,
    "moderate": 2,
    "minor": 1,
}

# Pinned axe-core CDN. Loaded once per Page (it is small, ~500KB) so we do
# not need a local copy in the Docker image.
AXE_CDN_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js"

# Run inside the page: returns the violations array as plain JSON.
AXE_RUN_SCRIPT = """
async () => {
  const result = await axe.run(document, {
    resultTypes: ['violations'],
  });
  return result.violations;
}
"""


def _normalise_violations(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Trim axe-core's verbose output to the fields the agent actually needs."""
    out: List[Dict[str, Any]] = []
    for v in raw or []:
        selectors: List[str] = []
        for node in v.get("nodes", []) or []:
            target = node.get("target") or []
            if target:
                # axe targets are arrays of CSS selectors (one per shadow level)
                selectors.append(" ".join(str(t) for t in target))
        out.append(
            {
                "rule_id": v.get("id", ""),
                "impact": v.get("impact") or "minor",
                "description": v.get("description", ""),
                "help": v.get("help", ""),
                "help_url": v.get("helpUrl", ""),
                "css_selectors": selectors,
                "node_count": len(v.get("nodes", []) or []),
            }
        )
    return out


def weighted_score(violations: List[Dict[str, Any]]) -> float:
    """Sum impact weights across all violation nodes."""
    total = 0.0
    for v in violations:
        w = IMPACT_WEIGHTS.get((v.get("impact") or "minor").lower(), 1)
        # weight per affected node so multiple instances of the same rule count
        total += w * max(int(v.get("node_count", 1)), 1)
    return float(total)


class AxeGrader:
    """Persistent Chromium browser instance for fast axe-core auditing."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        self._initialized = True

    async def run_audit(self, html_content: str) -> List[Dict[str, Any]]:
        """Run axe-core on the supplied HTML and return normalised violations."""
        if not self._initialized:
            await self.initialize()
        assert self._browser is not None

        page = await self._browser.new_page()
        try:
            await page.set_content(html_content or "<html></html>", wait_until="domcontentloaded")
            try:
                await page.add_script_tag(url=AXE_CDN_URL)
            except Exception:
                # Offline fallback: inject from local file if available.
                import os

                local = os.path.join(os.path.dirname(__file__), "axe.min.js")
                if os.path.exists(local):
                    await page.add_script_tag(path=local)
                else:
                    raise
            raw = await page.evaluate(AXE_RUN_SCRIPT)
            return _normalise_violations(raw)
        finally:
            await page.close()

    async def shutdown(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            if self._playwright is not None:
                await self._playwright.stop()
            self._browser = None
            self._playwright = None
            self._initialized = False


def compute_reward(
    original_violations: List[Dict[str, Any]],
    new_violations: List[Dict[str, Any]],
    original_html: str,
    fixed_html: str,
) -> float:
    """
    Reward = impact-weighted violation reduction with bonuses/penalties.

      base   = (orig_weight - new_weight) / orig_weight
      bonus  = +0.20 if zero violations remain
      pen    = -0.15 per *newly introduced* rule_id (not in the original set)

    Clamped to [0.0, 1.0]. If the original page had no violations, return 1.0
    when the fixed page also has none, otherwise 0.0.
    """
    orig_w = weighted_score(original_violations)
    new_w = weighted_score(new_violations)

    if orig_w <= 0:
        return 1.0 if new_w == 0 else 0.0

    base = (orig_w - new_w) / orig_w

    if len(new_violations) == 0:
        base += 0.20

    original_rule_ids = {v.get("rule_id") for v in original_violations}
    new_rule_ids = {v.get("rule_id") for v in new_violations}
    introduced = new_rule_ids - original_rule_ids
    base -= 0.15 * len(introduced)

    if base < 0.0:
        return 0.0
    if base > 1.0:
        return 1.0
    return float(base)


def format_violations_summary(violations: List[Dict[str, Any]]) -> str:
    """Human-readable summary an LLM agent can act on."""
    if not violations:
        return "No accessibility violations detected."
    lines: List[str] = [f"{len(violations)} violation rule(s) detected:"]
    for i, v in enumerate(violations, 1):
        sels = ", ".join(v.get("css_selectors", [])[:3]) or "(no selector)"
        lines.append(
            f"{i}. [{v.get('impact','minor').upper()}] {v.get('rule_id','')} — "
            f"{v.get('help','')}\n   Affected: {sels}\n   Fix: {v.get('description','')}"
        )
    return "\n".join(lines)
