from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any


DEFAULT_ACTOR_EMAIL = "guest@skillforge.local"


def build_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def build_token(prefix: str = "token") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def clone_json(value: Any) -> Any:
    return deepcopy(value)


def hash_password(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return hash_password(raw_password) == hashed_password


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    cleaned = "".join(char if char.isalnum() else " " for char in text)
    return " ".join(cleaned.split())


def slugify(value: Any) -> str:
    normalized = normalize_text(value).replace(" ", "-")
    return normalized or f"course-{int(datetime.utcnow().timestamp())}"


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def validate_email(value: Any) -> bool:
    text = normalize_email(value)
    return bool(text) and "@" in text and "." in text.split("@")[-1]


def format_number(value: Any) -> str:
    return f"{int(value or 0):,}"


def format_compact(value: Any) -> str:
    number = int(value or 0)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}".rstrip("0").rstrip(".") + "m"
    if number >= 1_000:
        return f"{number / 1_000:.1f}".rstrip("0").rstrip(".") + "k"
    return str(number)


def month_year_label(date: datetime | None = None) -> str:
    current = date or datetime.utcnow()
    return current.strftime("%B %Y")


def month_sort_stamp(date: datetime | None = None) -> int:
    current = date or datetime.utcnow()
    return (current.year * 100) + current.month


def json_dumps(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)
