from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any


PREVIEW_DOMAIN_ERROR_CODES = {
    "invalid_request",
    "logged_out",
    "capability_not_ready",
    "preview_failed",
}


class PreviewDomainError(Exception):
    def __init__(
        self,
        *,
        kind: str,
        capability: str,
        code: str,
        message: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code not in PREVIEW_DOMAIN_ERROR_CODES:
            raise ValueError(f"unsupported preview domain error code: {code}")
        self.kind = kind
        self.capability = capability
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or {"endpoint_matrix": [], "last_errors": []}

    def to_payload(self, *, source: str, checked_at: str) -> dict[str, Any]:
        return {
            "ok": False,
            "kind": self.kind,
            "source": source,
            "checked_at": checked_at,
            "capability": self.capability,
            "error": {
                "code": self.code,
                "message": self.message,
            },
            "diagnostics": {
                "endpoint_matrix": list(self.diagnostics.get("endpoint_matrix") or []),
                "last_errors": list(self.diagnostics.get("last_errors") or []),
            },
        }


def canonical_json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_preview_fingerprint(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def make_preview_id() -> str:
    return f"pvw_{secrets.token_hex(8)}"


def preview_state_from_blockers(blocking_issues: list[dict[str, Any]]) -> str:
    return "blocked" if blocking_issues else "preview_ready"
