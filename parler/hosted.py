"""Optional hosted admission boundary; the local CLI and pipeline remain independent."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .config import ParlerConfig
    from .pipeline import PipelineConfig
    from .pipeline.state import ProcessingState


class LongplayBilling(Protocol):
    """The public Longplay Python SDK's server methods used by this entry point."""

    def get_or_create_customer(self, *, external_user_id: str) -> Mapping[str, Any]: ...

    def check_entitlement(
        self, *, customer_id: str, internal_feature_id: str, quantity: str
    ) -> Mapping[str, Any]: ...


class HostedAccessError(RuntimeError):
    """Safe for a hosted API to translate to a denial/unavailable response."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _run_pipeline(input_path: str | Path, config: Any) -> Any:
    # Import after admission: denied requests do not initialize audio/model/cache machinery.
    from .pipeline import run_pipeline

    return run_pipeline(input_path, config)


def run_hosted_pipeline(
    input_path: str | Path,
    config: PipelineConfig | ParlerConfig,
    *,
    require_workspace: Callable[[], str],
    billing: LongplayBilling,
    access_feature_id: str,
    _runner: Callable[
        [str | Path, PipelineConfig | ParlerConfig], ProcessingState | None
    ] = _run_pipeline,
) -> ProcessingState | None:
    """Run existing processing only after host authentication and fresh workspace access.

    The host's callback must verify its session and workspace membership. Do not
    implement it by returning a workspace ID from a request body or selection cookie.
    Only a stable workspace ID and Feature go to billing, never audio or config.
    """
    workspace = require_workspace()
    if not isinstance(workspace, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", workspace):
        raise HostedAccessError("authentication_required", "A verified workspace is required.")
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", access_feature_id):
        raise HostedAccessError("billing_unavailable", "Hosted access is not configured.")
    try:
        customer = billing.get_or_create_customer(external_user_id=f"parler:workspace:{workspace}")
        result = billing.check_entitlement(
            customer_id=customer["customer"]["id"],
            internal_feature_id=access_feature_id,
            quantity="1",
        )
        check = result["check"]
        if check["kind"] != "access" or not isinstance(check["allowed"], bool):
            raise ValueError("Expected an access Feature")
        allowed = check["allowed"]
    except Exception:
        # SDK/provider exceptions may contain operational details; do not echo them to callers.
        raise HostedAccessError("billing_unavailable", "Could not verify hosted access.") from None
    if not allowed:
        raise HostedAccessError(
            "plan_required", "The workspace plan does not include hosted processing."
        )
    return _runner(input_path, config)
