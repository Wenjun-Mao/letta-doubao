import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from letta_client import Letta
from prompts.persona import PERSONAS, HUMAN_TEMPLATE
from prompts.system_prompts import (
    CHAT_V20260418_PROMPT,
)
from tests.shared.config_defaults import DEFAULT_CONTEXT_WINDOW_LIMIT, DEFAULT_LETTA_BASE_URL, DEFAULT_TEST_MODEL_HANDLE
from utils.message_parser import chat

DEFAULT_MODEL = DEFAULT_TEST_MODEL_HANDLE


def _memory_changed(chat_result: dict) -> bool:
    memory_diff = chat_result.get("memory_diff", {})
    return bool(memory_diff and memory_diff.get("old") != memory_diff.get("new"))


def _chat_with_memory_retry(client: Letta, agent_id: str, user_input: str, attempts: int = 3) -> tuple[dict, int]:
    """Retry the same semantic turn with a stronger memory-write hint when needed."""
    text = user_input
    last_result: dict | None = None

    for attempt in range(1, max(1, attempts) + 1):
        result = chat(client, agent_id, input=text)
        last_result = result
        if _memory_changed(result):
            return result, attempt

        text = user_input + " 请把这条信息更新到你的human记忆里，然后再回复我。"

    return last_result or {"sequence": [], "memory_diff": {"old": {}, "new": {}}}, attempts


def test_prompt(system_prompt, prompt_name) -> bool:
    print(f"\n{'='*60}")
    print(f"TESTING PROMPT STRATEGY: {prompt_name}")
    print(f"{'='*60}")
    
    client = Letta(base_url=DEFAULT_LETTA_BASE_URL)
    
    agent = client.agents.create(
        system=system_prompt,
        model=DEFAULT_MODEL,
        context_window_limit=DEFAULT_CONTEXT_WINDOW_LIMIT,
        memory_blocks=[
            {
                "label": "persona",
                "value": PERSONAS["chat_linxiaotang"],
            },
            {
                "label": "human",
                "value": HUMAN_TEMPLATE,
            },
        ],
    )
    
    print(f"Agent ID: {agent.id}")
    time.sleep(1) # Let db settle
    
    all_passed = True

    print("\n[Test 1] User supplies a name...")
    res, attempts_1 = _chat_with_memory_retry(client, agent.id, user_input="你好！我是张伟")
    
    tools_called = [s for s in res['sequence'] if s['type'] == 'tool_call']
    print(f"Tools explicitly invoked: {[t.get('name', str(t)) for t in tools_called]}")
    
    if _memory_changed(res):
        print("✅ Memory successfully modified!")
        print(f"Attempts used: {attempts_1}")
        # Quick hack to show the diff on human roughly
        print(f"New Memory: {res['memory_diff']['new'].get('human', '')}")
    else:
        all_passed = False
        print("❌ FAILED: Memory was not modified via tool calls. Internal Reasoning:")
        reasoning = [s for s in res['sequence'] if s['type'] == 'reasoning']
        if reasoning: print(f"   > {reasoning[0]['content']}")
        
    print("\n[Test 2] User supplies a hobby...")
    res2, attempts_2 = _chat_with_memory_retry(client, agent.id, user_input="我非常喜欢狗狗，你呢？")
    tools_called2 = [s for s in res2['sequence'] if s['type'] == 'tool_call']
    print(f"Tools explicitly invoked: {[t.get('name', str(t)) for t in tools_called2]}")
    
    if _memory_changed(res2):
        print("✅ Memory successfully modified!")
        print(f"Attempts used: {attempts_2}")
        print(f"New Memory: {res2['memory_diff']['new'].get('human', '')}")
    else:
        all_passed = False
        print("❌ FAILED: Memory was not modified via tool calls. Internal Reasoning:")
        reasoning2 = [s for s in res2['sequence'] if s['type'] == 'reasoning']
        if reasoning2: print(f"   > {reasoning2[0]['content']}")
        
    # Cleanup to save DB space
    client.agents.delete(agent_id=agent.id)

    return all_passed

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    ok = test_prompt(CHAT_V20260418_PROMPT, "CHAT_V20260418_PROMPT")
    if not ok:
        raise SystemExit(1)
