from __future__ import annotations

import json
import logging
import math
from typing import Any

from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_MAX_REPORTED_PATHS = 12


class GammaJSONResponse(JSONResponse):
    """JSON responses that degrade an uncomputable number instead of a whole reply.

    Starlette encodes with `allow_nan=False`, so a single NaN or infinity
    anywhere in a payload raises and the endpoint answers 500. A workspace is
    built from many independent providers and analytics, and one metric that
    cannot be computed should render as absence -- which is what the app already
    does with null -- not take every other section down with it.

    The strict encode is tried first, so a well-formed payload pays nothing. Only
    when it fails does the response get walked, and the offending paths are
    logged: nulling a value silently would hide a real analytics bug, and the
    place to fix it is always upstream of here.
    """

    def render(self, content: Any) -> bytes:
        try:
            return self._encode(content)
        except ValueError:
            sanitized, paths = _replace_non_finite(content)
            logger.warning(
                "Replaced %d non-finite value(s) with null to keep the response serializable: %s",
                len(paths),
                ", ".join(paths[:_MAX_REPORTED_PATHS]) or "unknown path",
            )
            return self._encode(sanitized)

    @staticmethod
    def _encode(content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


def _replace_non_finite(node: Any, path: str = "$") -> tuple[Any, list[str]]:
    if isinstance(node, float):
        if math.isfinite(node):
            return node, []
        return None, [path]
    if isinstance(node, dict):
        result: dict[Any, Any] = {}
        paths: list[str] = []
        for key, value in node.items():
            cleaned, found = _replace_non_finite(value, f"{path}.{key}")
            result[key] = cleaned
            paths.extend(found)
        return result, paths
    if isinstance(node, (list, tuple)):
        items: list[Any] = []
        paths = []
        for index, value in enumerate(node):
            cleaned, found = _replace_non_finite(value, f"{path}[{index}]")
            items.append(cleaned)
            paths.extend(found)
        return items, paths
    return node, []
