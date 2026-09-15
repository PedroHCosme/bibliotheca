"""Parse `claude -p --output-format stream-json --verbose` output into one run record."""
import json

USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens", "output_tokens")


def parse(lines) -> dict:
    init, result, tool_calls, usage_by_id = {}, None, [], {}
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        event = json.loads(line)
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            init = event
        elif kind == "assistant":
            message = event["message"]
            usage_by_id[message.get("id")] = message.get("usage", {})
            for block in message.get("content", []):
                if block.get("type") == "tool_use":
                    tool_calls.append({"name": block["name"],
                                       "input": block.get("input", {})})
        elif kind == "result":
            result = event
    if result is None:
        raise ValueError("transcript has no result event")
    return {
        "answer": result.get("result", ""),
        "is_error": bool(result.get("is_error", False)),
        "tokens": sum(u.get(k, 0) for u in usage_by_id.values() for k in USAGE_KEYS),
        "result_usage": result.get("usage", {}),
        "num_turns": result.get("num_turns"),
        "tool_calls": tool_calls,
        "init_tools": init.get("tools", []),
        "init_skills": init.get("skills", []),
        "init_plugins": init.get("plugins", []),
    }


def used_biblio(tool_calls) -> bool:
    """True when the agent ran the biblio CLI — a contamination flag for arms A and C."""
    return any(c["name"] == "Bash" and "biblio" in str(c["input"].get("command", "")).lower()
               for c in tool_calls)
