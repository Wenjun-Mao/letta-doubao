from __future__ import annotations

import json
from typing import Any

from letta_client import Letta


def _json_dump(value: Any) -> str:
    """Serialize values with UTF-8-friendly JSON for UI readability."""
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def _normalize_text_content(content: Any) -> str:
    """Normalize message content to display-safe UTF-8 text."""
    if content is None:
        return ""
    if isinstance(content, str):
        stripped = content.strip()
        if not stripped:
            return ""
        # Decode JSON-looking text so escaped Chinese shows as real characters.
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                return _json_dump(parsed)
            except Exception:
                return content
        return content
    if isinstance(content, list):
        text_parts = [getattr(item, "text", None) for item in content]
        valid_parts = [part for part in text_parts if isinstance(part, str) and part]
        if valid_parts:
            return " ".join(valid_parts)
        return _json_dump(content)
    if isinstance(content, (dict, tuple)):
        return _json_dump(content)
    return str(content)


def _normalize_tool_arguments(arguments: Any) -> str:
    """Convert tool call args to readable JSON while preserving non-JSON text."""
    if arguments is None:
        return ""
    if isinstance(arguments, (dict, list, tuple)):
        return _json_dump(arguments)
    if isinstance(arguments, str):
        stripped = arguments.strip()
        if not stripped:
            return ""
        try:
            parsed = json.loads(stripped)
            return _json_dump(parsed)
        except Exception:
            return arguments
    return str(arguments)

def get_agent_memory_dict(client: Letta, agent_id: str) -> dict:
    """Returns a dictionary of {block_label: block_value}"""
    blocks = client.agents.blocks.list(agent_id=agent_id)
    return {b.label: b.value for b in blocks}

def _parse_message_content(msg) -> dict[str, Any]:
    m_type = getattr(msg, "message_type", "unknown")
    if m_type == "user_message":
        content = _normalize_text_content(getattr(msg, "content", ""))
        return {"type": "user", "content": content}
    elif m_type == "reasoning_message":
        reasoning = _normalize_text_content(getattr(msg, "reasoning", "") or "")
        return {"type": "reasoning", "content": reasoning.strip()}
    elif m_type == "assistant_message":
        content = _normalize_text_content(getattr(msg, "content", ""))
        return {"type": "assistant", "content": content or ""}
    elif m_type == "tool_call_message":
        tool_call = getattr(msg, "tool_call", None)
        name = getattr(tool_call, "name", "unknown_tool") if tool_call else "unknown_tool"
        args = getattr(tool_call, "arguments", "") if tool_call else ""
        return {
            "type": "tool_call",
            "name": name,
            "arguments": _normalize_tool_arguments(args),
        }
    elif m_type == "tool_return_message":
        status = getattr(msg, "status", "")
        content = getattr(msg, "tool_return", getattr(msg, "content", ""))
        return {
            "type": "tool_return",
            "status": status,
            "content": _normalize_text_content(content),
        }
    return {"type": "unknown", "content": _normalize_text_content(msg)}

def chat(client: Letta, agent_id: str, **kwargs) -> dict:
    """
    Core conversational API generator.
    Returns structured dict with sequences, memory diffs, and execution steps.
    """
    old_mem = get_agent_memory_dict(client, agent_id)
    
    response = client.agents.messages.create(
        agent_id=agent_id,
        **kwargs
    )
    
    new_mem = get_agent_memory_dict(client, agent_id)
    
    steps = []
    messages = response.messages or []
    for msg in messages:
        if getattr(msg, "message_type", "") == "system_message":
            continue
        parsed = _parse_message_content(msg)
        steps.append(parsed)
        
    return {
        "total_steps": len(steps),
        "sequence": steps,
        "memory_diff": {
            "old": old_mem,
            "new": new_mem
        },
        "raw_messages": response.messages  # Optional, keeps raw Letta models around just in case
    }

def pretty_print_messages(chat_result: dict, focus_block: str = "human"):
    """
    Takes the structured result from chat() and prints it beautifully for notebooks.
    """
    print("\n" + "="*50)
    print(f"🔹 TOTAL STEPS TAKEN: {chat_result['total_steps']}")
    print("="*50)
    
    for i, step in enumerate(chat_result['sequence'], 1):
        step_str = f"[Step {i}]"
        
        # fallback for python < 3.10 if we want to avoid Match-Case, but python 3.10+ is safe here
        if step['type'] == 'user':
            print(f"{step_str} 👤 USER: {step['content']}")
        elif step['type'] == 'reasoning':
            print(f"{step_str} 🧠 INTERNAL (Reasoning):\n  {step['content']}")
        elif step['type'] == 'assistant':
            print(f"{step_str} 🗣️ ASSISTANT (Lin Xiao Tang):\n  {step['content']}")
        elif step['type'] == 'tool_call':
            print(f"{step_str} 🔧 TOOL CALLED [{step.get('name')}]:\n  Arguments: {step.get('arguments')}")
        elif step['type'] == 'tool_return':
            print(f"{step_str} ✅ TOOL RETURN [{step.get('status')}]: {step.get('content')}")
        else:
            print(f"{step_str} ❓ UNKNOWN:\n  {step.get('content')}")
            
        print("-" * 50)
        
    # Print Memory Diff
    old_mem = chat_result['memory_diff']['old']
    new_mem = chat_result['memory_diff']['new']
    
    if old_mem and new_mem:
        old_val = old_mem.get(focus_block, "")
        new_val = new_mem.get(focus_block, "")
        if old_val != new_val:
            print(f"📝 MEMORY CHANGED [{focus_block}]:")
            print(f"  [-] BEFORE:\n{old_val}")
            print(f"  [+] AFTER:\n{new_val}")
        else:
            print(f"📝 MEMORY UNCHANGED [{focus_block}]")
    print("="*50)

def chat_and_print(client: Letta, agent_id: str, **kwargs):
    """Notebook wrapper combining structural chat generation with pretty printing"""
    result = chat(client, agent_id, **kwargs)
    pretty_print_messages(result)
    return result
