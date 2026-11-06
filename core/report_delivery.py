"""Bounded report copy for an already authorized analysis response."""
import base64
import hashlib

MAX_INLINE_REPORT_BYTES = 8 * 1024 * 1024


def attach_report_copy(payload, filename, content, requested, max_bytes=MAX_INLINE_REPORT_BYTES):
    if not requested:
        return payload
    if len(content) <= max_bytes:
        payload["report_file"] = {"filename": filename, "content_base64": base64.b64encode(content).decode("ascii"),
                                  "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        payload["report_delivery"] = "inline_and_link"
    else:
        payload.update(report_delivery="link_only", report_inline_reason="size_limit")
    return payload
