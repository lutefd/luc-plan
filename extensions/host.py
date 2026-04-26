#!/usr/bin/env python3
"""luc-plan extension host.

Implements the luc.extension/v1 JSONL protocol directly. The host keeps the
current plan in luc session extension storage and exposes hosted tool handlers
for updating and rendering it.
"""

from __future__ import annotations

import json
import sys
from typing import Any

KNOWN_STATUSES = {"pending", "active", "done", "blocked", "canceled"}
STATUS_MARKS = {
    "pending": "[ ]",
    "active": "[>]",
    "done": "[x]",
    "blocked": "[!]",
    "canceled": "[-]",
}
STATUS_LABELS = {
    "pending": "Pending",
    "active": "Started",
    "done": "Completed",
    "blocked": "Blocked",
    "canceled": "Canceled",
}
STATUS_EMOJI = {
    "pending": "⏳",
    "active": "▶️",
    "done": "✅",
    "blocked": "⛔",
    "canceled": "🚫",
}

session_store: dict[str, Any] = {}


def emit(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def log(message: str) -> None:
    emit({"type": "log", "level": "info", "message": message})


def current_plan() -> dict[str, Any] | None:
    plan = session_store.get("plan")
    if isinstance(plan, dict) and isinstance(plan.get("items"), list):
        return plan
    return None


def normalize_item(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError("each plan item must be an object")
    item_id = str(raw.get("id") or "").strip()
    text = str(raw.get("text") or "").strip()
    status = str(raw.get("status") or "").strip()
    if not item_id:
        raise ValueError("plan item ids must be non-empty")
    if not text:
        raise ValueError(f"plan item {item_id!r} text must be non-empty")
    if status not in KNOWN_STATUSES:
        raise ValueError(f"plan item {item_id!r} has unknown status {status!r}")
    return {"id": item_id, "text": text, "status": status}


def normalize_items(raw_items: Any) -> list[dict[str, str]]:
    if not isinstance(raw_items, list):
        raise ValueError("items must be an array")
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for raw in raw_items:
        item = normalize_item(raw)
        if item["id"] in seen:
            raise ValueError(f"duplicate plan item id {item['id']!r}")
        seen.add(item["id"])
        items.append(item)
    return items


def tool_arguments(msg: dict[str, Any]) -> dict[str, Any]:
    tool = msg.get("tool")
    if isinstance(tool, dict) and isinstance(tool.get("arguments"), dict):
        return tool["arguments"]
    if isinstance(msg.get("arguments"), dict):
        return msg["arguments"]
    return {}


def diff_plan(old_items: list[dict[str, str]], new_items: list[dict[str, str]]) -> list[str]:
    old_by_id = {item["id"]: item for item in old_items}
    new_by_id = {item["id"]: item for item in new_items}
    changes: list[str] = []

    for item in new_items:
        if item["id"] not in old_by_id:
            changes.append(f"- ➕ Added: {item['text']}")

    for item in old_items:
        if item["id"] not in new_by_id:
            changes.append(f"- ➖ Removed: {item['text']}")

    for item in new_items:
        old = old_by_id.get(item["id"])
        if old is None:
            continue
        if old["status"] != item["status"]:
            emoji = STATUS_EMOJI[item["status"]]
            label = STATUS_LABELS[item["status"]]
            changes.append(f"- {emoji} {label}: {item['text']}")
        if old["text"] != item["text"]:
            changes.append(f"- ✏️ Renamed: {old['text']} → {item['text']}")

    old_common_order = [item["id"] for item in old_items if item["id"] in new_by_id]
    new_common_order = [item["id"] for item in new_items if item["id"] in old_by_id]
    if old_common_order != new_common_order:
        changes.append("- ↕️ Reordered plan items")

    return changes


def render_plan_items(items: list[dict[str, str]]) -> str:
    return "\n".join(f"- {STATUS_MARKS[item['status']]} {item['text']}" for item in items)


def render_status() -> str:
    plan = current_plan()
    if not plan or not plan.get("items"):
        return "_No active plan._"
    return "### Current Plan\n\n" + render_plan_items(plan["items"])


def render_timeline_note(
    previous: dict[str, Any] | None,
    title: str,
    note: str,
    items: list[dict[str, str]],
) -> tuple[str, str]:
    previous_items = previous.get("items", []) if previous else []
    heading = "Updated Plan" if previous_items else "Created Plan"
    intro_parts = []
    if title:
        intro_parts.append(f"**{title}**")
    if note:
        intro_parts.append(f"_{note}_")
    intro = ("\n\n" + "\n\n".join(intro_parts)) if intro_parts else ""

    if not previous_items:
        body = f"### {heading}{intro}\n\n{render_plan_items(items)}"
    else:
        changes = diff_plan(previous_items, items)
        changed = "\n".join(changes) if changes else "- No visible changes"
        body = f"### {heading}{intro}\n\nChanged:\n{changed}\n\nCurrent:\n{render_plan_items(items)}"
    return heading, body


def save_plan(plan: dict[str, Any]) -> None:
    session_store["plan"] = plan
    emit({"type": "storage_update", "scope": "session", "value": session_store})


def handle_update_plan(msg: dict[str, Any]) -> None:
    request_id = msg.get("request_id")
    try:
        args = tool_arguments(msg)
        title = str(args.get("title") or "").strip()
        note = str(args.get("note") or "").strip()
        items = normalize_items(args.get("items"))
        previous = current_plan()
        plan = {"title": title, "note": note, "items": items}
        save_plan(plan)
        heading, body = render_timeline_note(previous, title, note, items)
        emit(
            {
                "type": "client_action",
                "action": {
                    "id": f"plan-note-{request_id or 'update'}",
                    "kind": "timeline.note",
                    "title": heading,
                    "body": body,
                    "render": "markdown",
                },
            }
        )
        emit(
            {
                "type": "client_action",
                "action": {
                    "id": f"plan-refresh-{request_id or 'update'}",
                    "kind": "view.refresh",
                    "view_id": "plan.current",
                },
            }
        )
        emit(
            {
                "type": "tool_result",
                "request_id": request_id,
                "result": {
                    "content": "Plan updated.",
                    "collapsed_summary": "Plan updated",
                },
            }
        )
    except ValueError as exc:
        emit(
            {
                "type": "tool_result",
                "request_id": request_id,
                "result": {
                    "content": f"Plan update rejected: {exc}",
                    "collapsed_summary": "Plan update rejected",
                },
            }
        )


def handle_status(msg: dict[str, Any]) -> None:
    emit(
        {
            "type": "tool_result",
            "request_id": msg.get("request_id"),
            "result": {
                "content": render_status(),
                "collapsed_summary": "Current plan",
            },
        }
    )


def hidden_context() -> list[str]:
    plan = current_plan()
    if not plan or not plan.get("items"):
        return []
    lines = ["Current task plan:"]
    lines.extend(f"- {item['status']}: {item['text']}" for item in plan["items"])
    return ["\n".join(lines)]


def handle_prompt_context(msg: dict[str, Any]) -> None:
    emit(
        {
            "type": "decision",
            "request_id": msg.get("request_id"),
            "hidden_context": hidden_context(),
        }
    )


def handle_message(msg: dict[str, Any]) -> bool:
    global session_store

    kind = msg.get("type")
    if kind == "hello":
        emit({"type": "ready", "protocol_version": 1})
    elif kind == "storage_snapshot":
        snapshot = msg.get("session")
        session_store = snapshot if isinstance(snapshot, dict) else {}
    elif kind == "event" and msg.get("event") == "prompt.context":
        handle_prompt_context(msg)
    elif kind == "tool_invoke":
        handler = msg.get("handler")
        if handler == "update_plan":
            handle_update_plan(msg)
        elif handler == "status":
            handle_status(msg)
        else:
            emit(
                {
                    "type": "tool_result",
                    "request_id": msg.get("request_id"),
                    "result": {
                        "content": f"Unknown plan handler: {handler}",
                        "collapsed_summary": "Unknown plan handler",
                    },
                }
            )
    elif kind == "ping":
        emit({"type": "ready", "protocol_version": 1})
    elif kind == "session_shutdown":
        return False
    return True


def main() -> int:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
            if isinstance(msg, dict) and not handle_message(msg):
                break
        except Exception as exc:  # noqa: BLE001 - report protocol diagnostics, keep host alive.
            emit({"type": "error", "error": str(exc)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
