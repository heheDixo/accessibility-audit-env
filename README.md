---
title: Accessibility Audit Env
emoji: ♿
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
tags:
  - openenv
  - hackathon
---

# AccessibilityAudit-Env

An OpenEnv environment where an AI agent must fix **WCAG 2.1 accessibility
violations** in real HTML pages. Grading is performed by **axe-core** — the
industry-standard accessibility engine (3B+ npm downloads/year) — driven by
a persistent headless Chromium via Playwright. Built for the Meta x Scaler
OpenEnv Hackathon (Round 1).

## Why this environment?

- **Real-world impact.** Web accessibility is a legal requirement in the
  US (ADA), EU (EAA), and many other jurisdictions. There are 4,000+ ADA
  web accessibility lawsuits filed in the US per year. Over a billion
  people worldwide have a disability that affects their use of the web.
- **No existing RL benchmark.** Code-fix benchmarks focus on functional
  bugs; nothing rewards accessibility-fix capability.
- **Deterministic grading.** axe-core gives the same answer every time —
  no LLM-as-judge, no hidden randomness.

## How it works

1. `reset(task_id)` returns an HTML page with planted WCAG violations and
   the axe-core violation list.
2. The agent submits **complete corrected HTML** via `step(fixed_html=...)`.
3. The grader re-runs axe-core on the new HTML, computes an
   impact-weighted reward, and returns the updated violations so the
   agent can iterate (up to 5 steps).

## Action space

```python
AccessibilityAuditAction(fixed_html: str)
```

## Observation space

```python
AccessibilityAuditObservation(
    html_source: str,                    # current HTML
    violations: list[dict],              # axe-core violations
    task_id: str,                        # easy | medium | hard
    task_description: str,               # human-readable
    violation_count: int,
    violation_summary: str,              # formatted for LLM
    done: bool,
    reward: float,
)
```

Each violation dict contains: `rule_id`, `impact`, `description`, `help`,
`help_url`, `css_selectors`, `node_count`.

## Tasks

| Task   | Difficulty | Page                | Planted violations | Categories |
|--------|------------|---------------------|--------------------|------------|
| easy   | Easy       | Marketing landing   | ~2                 | image-alt, label |
| medium | Medium     | Analytics dashboard | ~5–7               | heading-order, link-name, color-contrast, landmark-one-main, fieldset |
| hard   | Hard       | CRM web app         | 15+                | html-has-lang, image-alt, button-name, label, select-name, autocomplete-valid, aria-dialog-name, aria-hidden-focus, color-contrast, skip-link, duplicate-id, th-has-data-cells, aria-required-children, aria-input-field-name, label-content-name-mismatch |
| expert | Expert     | E-commerce checkout | 12+                | html-has-lang, link-name, label, select-name, autocomplete-valid (cc-number/cc-exp/postal-code/street-address/tel), color-contrast (placeholder + link), duplicate-id, aria-hidden-focus, label-content-name-mismatch, aria-input-field-name, th-has-data-cells |

## Reward function

```
orig_w  = sum(impact_weight * node_count) over original violations
new_w   = sum(impact_weight * node_count) over remaining violations
base    = (orig_w - new_w) / orig_w
bonus   = +0.20 if zero violations remain
penalty = -0.15 per newly introduced rule_id (regression)
reward  = clamp(base + bonus - penalty, 0.0, 1.0)
```

Impact weights: `critical=4, serious=3, moderate=2, minor=1`.

## Setup

```bash
pip install -e .
playwright install chromium --with-deps
docker build -f server/Dockerfile -t accessibility_audit_env .
docker run --rm -p 7860:7860 accessibility_audit_env
```

## Environment variables (used by `inference.py`)

| Variable      | Default                                  |
|---------------|------------------------------------------|
| `API_BASE_URL`| `https://router.huggingface.co/v1`       |
| `MODEL_NAME`  | `Qwen/Qwen2.5-72B-Instruct`              |
| `HF_TOKEN`    | (required)                               |
| `IMAGE_NAME`  | `accessibility_audit_env:latest`         |

## Baseline scores

| Task   | Model                       | Score |
|--------|-----------------------------|-------|
| easy   | Qwen/Qwen2.5-72B-Instruct   | 1.00  |
| medium | Qwen/Qwen2.5-72B-Instruct   | 1.00  |
| hard   | Qwen/Qwen2.5-72B-Instruct   | 0.87  |
| expert | Qwen/Qwen2.5-72B-Instruct   | 1.00  |
