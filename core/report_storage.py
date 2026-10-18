"""Shared location and safe names for generated reports."""

import os
import re
from pathlib import Path
from uuid import uuid4


def report_directory() -> Path:
    return Path(os.environ.get("REPORT_OUTPUT_DIR") or "data/output")


def _safe_name_part(value: object) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value))
    return name.strip(" .")[:60] or "unknown"


def new_report_path(course_name: object, session: object) -> Path:
    directory = report_directory()
    directory.mkdir(parents=True, exist_ok=True)
    course = _safe_name_part(course_name)
    period = _safe_name_part(session)
    return directory / f"{course}_{period}_{uuid4().hex}_分析报告.xlsx"
