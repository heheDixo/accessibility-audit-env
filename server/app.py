"""FastAPI app for the AccessibilityAudit OpenEnv server."""
from ..models import AccessibilityAuditAction, AccessibilityAuditObservation
from .accessibility_audit_environment import AccessibilityAuditEnvironment

try:
    # Newer openenv-core
    from openenv.core.env_server import create_fastapi_app  # type: ignore

    _factory = create_fastapi_app
except ImportError:  # pragma: no cover
    from openenv.core.env_server import create_app  # type: ignore

    _factory = create_app

app = _factory(
    AccessibilityAuditEnvironment,
    AccessibilityAuditAction,
    AccessibilityAuditObservation,
)


@app.get("/")
def root():
    return {
        "name": "accessibility_audit_env",
        "status": "ok",
        "description": "OpenEnv environment: fix WCAG violations in HTML, graded by axe-core.",
        "endpoints": ["/health", "/reset", "/step"],
        "tasks": ["easy", "medium", "hard", "expert"],
    }


def main() -> None:
    """Entry point for `accessibility-audit-server` console script."""
    import os
    import uvicorn

    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(
        "accessibility_audit_env.server.app:app",
        host="0.0.0.0",
        port=port,
        ws_ping_interval=None,
        ws_ping_timeout=None,
        timeout_keep_alive=600,
    )


if __name__ == "__main__":
    main()
