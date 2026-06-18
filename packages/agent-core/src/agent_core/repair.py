"""Tool argument repair — fix LLM mistakes before execution."""

import difflib
import json
import logging
from typing import Any

from agent_core.models import ToolCall

logger = logging.getLogger(__name__)


class RepairFailedError(Exception):
    pass


class ToolArgRepairer:
    """Multi-strategy tool argument repair before execution."""

    async def repair(self, tool_call: ToolCall, tool_schema: dict[str, Any]) -> ToolCall:
        """Fix common LLM argument mistakes."""
        args = tool_call.arguments
        schema = tool_schema.get("input_schema", {})
        props = schema.get("properties", {})
        required = schema.get("required", [])

        # Strategy 1: JSON parse + re-serialize.
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = self._repair_truncated_json(args)

        # Strategy 2: Type coercion.
        args = self._coerce_types(args, props)

        # Strategy 3: Missing required fields.
        args = self._fill_defaults(args, props, required)

        # Strategy 4: Extra field removal.
        args = {k: v for k, v in args.items() if k in props or not props}

        # Strategy 5: Field name fuzzy match.
        args = self._fuzzy_fields(args, props)

        return ToolCall(id=tool_call.id, name=tool_call.name, arguments=args)

    @staticmethod
    def _coerce_types(args: dict, props: dict) -> dict:
        for key, spec in props.items():
            if key not in args:
                continue
            target = spec.get("type", "string")
            val = args[key]
            if target == "integer" and isinstance(val, str):
                try:
                    args[key] = int(val)
                except ValueError:
                    pass
            elif target == "number" and isinstance(val, str):
                try:
                    args[key] = float(val)
                except ValueError:
                    pass
            elif target == "boolean" and isinstance(val, str):
                if val.lower() in ("true", "1", "yes"):
                    args[key] = True
                elif val.lower() in ("false", "0", "no"):
                    args[key] = False
        return args

    @staticmethod
    def _fill_defaults(args: dict, props: dict, required: list) -> dict:
        for field in required:
            if field not in args:
                spec = props.get(field, {})
                d = spec.get("default")
                if d is not None:
                    args[field] = d
                elif spec.get("type") == "string":
                    args[field] = ""
                elif spec.get("type") == "integer":
                    args[field] = 0
        return args

    @staticmethod
    def _fuzzy_fields(args: dict, props: dict) -> dict:
        prop_keys = list(props.keys())
        new_args: dict[str, Any] = {}
        for key, val in args.items():
            if key in props:
                new_args[key] = val
            else:
                matches = difflib.get_close_matches(key, prop_keys, n=1, cutoff=0.8)
                if matches:
                    new_args[matches[0]] = val
                else:
                    new_args[key] = val
        return new_args

    @staticmethod
    def _repair_truncated_json(raw: str) -> dict[str, Any]:
        # Balance brackets in truncated JSON.
        open_brackets = raw.count("{") - raw.count("}")
        open_square = raw.count("[") - raw.count("]")
        raw += "}" * max(0, open_brackets)
        raw += "]" * max(0, open_square)
        # Close last string if unclosed.
        if raw.count('"') % 2 != 0:
            raw += '"'
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise RepairFailedError(f"Cannot repair: {raw[:100]}")
