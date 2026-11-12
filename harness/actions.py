"""Parse model actions without evaluating code or repairing incomplete JSON."""
import json


FIELDS = {
    "answer": {"action", "answer"},
    "abstain": {"action", "reason"},
    "read": {"action", "path"},
    "python": {"action", "code"},
    "write": {"action", "path", "content"},
    "edit": {"action", "path", "old_text", "new_text"},
}


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_action(content, *, recover=False):
    """Return (action, parse_mode); recovery accepts one complete terminal object.

    Recovery never chooses among multiple objects, completes a fragment, or
    executes prose. The existing dispatcher still checks task/tool permissions.
    """
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        _, newline, block = text.partition("\n")
        if not newline:
            raise ValueError("incomplete code fence")
        text = block.rsplit("```", 1)[0].strip()
    decoder = json.JSONDecoder(object_pairs_hook=_unique_keys)
    try:
        action = decoder.decode(text)
        mode = "strict"
    except ValueError:
        if not recover:
            raise
        start = text.find("{")
        if start < 0 or "}" in text[:start]:
            raise ValueError("no unambiguous terminal JSON action") from None
        action, end = decoder.raw_decode(text, start)
        tail = text[end:].strip()
        prefix = text[:start]
        if tail:
            # A terminal fenced object is allowed; extra braces, explanation,
            # or a second object are not discarded.
            if tail != "```" or not prefix.rstrip().endswith(("```json", "```")):
                raise ValueError("extra content after JSON action")
        mode = "recovered"
    if not isinstance(action, dict):
        raise ValueError("action must be a JSON object")
    if mode == "recovered":
        kind = action.get("action")
        if not isinstance(kind, str) or kind not in FIELDS or set(action) != FIELDS[kind]:
            raise ValueError("recovered object must match one declared action schema")
        if any(not isinstance(value, str) for value in action.values()):
            raise ValueError("recovered action fields must be strings")
    return action, mode
