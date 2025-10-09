"""Chart utilities shared across agents and UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class ChartSpec:
    kind: str
    x: Optional[str] = None
    y: Optional[str] = None
    color: Optional[str] = None
    bins: Optional[int] = None
    aggfunc: Optional[str] = None


def extract_chart_spec_from_text(text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    start = text.rfind("<<CHART_SPEC>>")
    end = text.rfind("<<END_CHART_SPEC>>")
    if start == -1 or end == -1 or end <= start:
        return text, None
    json_block = text[start + len("<<CHART_SPEC>>"):end].strip()
    try:
        data = json.loads(json_block)
    except json.JSONDecodeError:
        return text.strip(), None
    cleaned = text[:start].rstrip()
    return cleaned, data


def normalize_chart_spec(data: Dict[str, Any]) -> Optional[ChartSpec]:
    if not isinstance(data, dict):
        return None
    kind = data.get("kind") or data.get("tipo")
    if not kind:
        return None
    return ChartSpec(
        kind=kind,
        x=data.get("x"),
        y=data.get("y"),
        color=data.get("color"),
        bins=data.get("bins"),
        aggfunc=data.get("agg") or data.get("aggfunc"),
    )
