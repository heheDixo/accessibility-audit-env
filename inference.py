#!/usr/bin/env python3
"""
Inference Script for AccessibilityAudit-Env
============================================
MANDATORY STDOUT FORMAT:
[START] task=<task_name> env=<benchmark> model=<model_name>
[STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
[END]   success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>
"""
from __future__ import annotations

import asyncio
import os
import textwrap
from typing import List, Optional

from openai import OpenAI

from accessibility_audit_env import AccessibilityAuditAction, AccessibilityAuditEnv

IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME") or os.getenv("IMAGE_NAME", "accessibility_audit_env:latest")
HF_TOKEN = os.getenv("HF_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")

BENCHMARK = "accessibility_audit"
MAX_STEPS = 5
TEMPERATURE = 0.3
MAX_TOKENS = 4096

TASKS = ["easy", "medium", "hard", "expert"]

SYSTEM_PROMPT = textwrap.dedent(
    """
    You are a web accessibility expert. You receive HTML pages with WCAG 2.1
    accessibility violations. Your job is to fix ALL violations while preserving
    the page's visual appearance and functionality.

    You will receive:
    1. The current HTML source
    2. A list of accessibility violations detected by axe-core (with rule IDs,
       impact levels, CSS selectors, and fix guidance)

    You must respond with the COMPLETE corrected HTML. Do not explain — just
    output the fixed HTML. Make surgical, minimal fixes. Do not rewrite the
    entire page.

    Common fixes:
    - Missing alt text: add descriptive alt attributes to <img>
    - Missing labels: add <label for="..."> associated with form inputs
    - Color contrast: change colors to meet WCAG AA (4.5:1 ratio)
    - Heading hierarchy: do not skip heading levels
    - ARIA roles: add role/aria-* on dialogs, tabs, etc.
    - Landmark regions: wrap content in <main>, <nav>, <header>, <footer>
    - Link text: replace "Click here" with descriptive link text
    - Skip navigation: add a skip-to-content link
    - <html> must have a lang attribute
    - Address fields need autocomplete attributes

    Output ONLY the complete HTML. No markdown, no explanation, no code fences.
    """
).strip()


def log_start(task: str, env_name: str, model: str) -> None:
    print(f"[START] task={task} env={env_name} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    action_short = action[:100].replace("\n", " ")
    if len(action) > 100:
        action_short += "..."
    print(
        f"[STEP] step={step} action={action_short} reward={reward:.4f} "
        f"done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.4f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} rewards={rewards_str}",
        flush=True,
    )


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```html"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def get_fix_from_llm(
    client: OpenAI, html: str, violations_summary: str, step: int
) -> str:
    user_prompt = (
        f"Step {step}: Fix the following accessibility violations in this HTML.\n\n"
        f"VIOLATIONS DETECTED:\n{violations_summary}\n\n"
        f"CURRENT HTML:\n{html}\n\n"
        "Output the COMPLETE fixed HTML only. No explanation."
    )
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        text = (completion.choices[0].message.content or "").strip()
        return _strip_fences(text) or html
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return html


def _obs(result):
    """Support both `result.observation` and result-as-observation shapes."""
    return getattr(result, "observation", result)


async def run_task(client: OpenAI, env, task_id: str) -> float:
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=task_id, env_name=BENCHMARK, model=MODEL_NAME)

    try:
        result = await env.reset(task_id=task_id)
        obs = _obs(result)

        for step in range(1, MAX_STEPS + 1):
            if getattr(obs, "done", False):
                break

            fixed_html = get_fix_from_llm(
                client,
                getattr(obs, "html_source", ""),
                getattr(obs, "violation_summary", ""),
                step,
            )

            action_str = f"submit_html(len={len(fixed_html)})"
            try:
                result = await env.step(AccessibilityAuditAction(fixed_html=fixed_html))
            except Exception as step_exc:
                steps_taken = step
                rewards.append(1e-3)
                log_step(step, action_str, 1e-3, True, str(step_exc))
                raise

            obs = _obs(result)
            reward = float(getattr(result, "reward", None) or getattr(obs, "reward", 1e-3) or 1e-3)
            # Hard guarantee: every reward we report stays strictly inside (0, 1).
            EPS = 1e-3
            if reward <= 0.0:
                reward = EPS
            elif reward >= 1.0:
                reward = 1.0 - EPS
            done = bool(getattr(result, "done", False) or getattr(obs, "done", False))

            rewards.append(reward)
            steps_taken = step
            log_step(step, action_str, reward, done, None)

            if done:
                break

        EPS = 1e-3
        raw = rewards[-1] if rewards else EPS
        score = max(EPS, min(1.0 - EPS, raw))
        success = score > 0.1

    except Exception as exc:
        print(f"[DEBUG] Task {task_id} error: {exc}", flush=True)
        success = False
    finally:
        log_end(success=success, steps=steps_taken, rewards=rewards)

    return score


async def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    remote_url = os.getenv("AAE_REMOTE_URL", "").strip().rstrip("/")
    provider = None
    if remote_url:
        base_url = remote_url
        print(f"[DEBUG] Using remote env at {base_url}", flush=True)
    else:
        import subprocess
        host_port = 8765
        container_name = "aae_inference_run"
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        subprocess.run(
            ["docker", "run", "-d", "--rm", "--name", container_name,
             "-p", f"{host_port}:7860", IMAGE_NAME],
            check=True, capture_output=True,
        )
        from openenv.core.containers.runtime.providers import LocalDockerProvider
        provider = LocalDockerProvider()
        base_url = f"http://localhost:{host_port}"
        provider.wait_for_ready(base_url, timeout_s=180.0)

    env = AccessibilityAuditEnv(base_url=base_url, provider=provider)
    await env.connect()
    try:
        for task_id in TASKS:
            score = await run_task(client, env, task_id)
            print(f"[DEBUG] Task {task_id} final score: {score:.3f}", flush=True)
    finally:
        try:
            await env.close()
        except Exception as exc:
            print(f"[DEBUG] env.close() error: {exc}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
