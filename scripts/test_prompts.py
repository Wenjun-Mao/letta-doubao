import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from letta_client import Letta
from prompts.persona import PERSONAS, HUMAN_TEMPLATE
from prompts.system_prompts import CUSTOM_V1_PROMPT, AGGRESSIVE_MEMORY_PROMPT, STRUCTURED_MEMORY_PROMPT, TOOLS_FIRST_PROMPT
from utils.message_parser import chat

def test_prompt(system_prompt, prompt_name):
    print(f"\n{'='*60}")
    print(f"TESTING PROMPT STRATEGY: {prompt_name}")
    print(f"{'='*60}")
    
    client = Letta(base_url="http://localhost:8283")
    
    agent = client.agents.create(
        system=system_prompt,
        model="lmstudio_openai/qwen/qwen3.5-35b-a3b",
        context_window_limit=16384,
        memory_blocks=[
            {
                "label": "persona",
                "value": PERSONAS["linxiaotang"],
            },
            {
                "label": "human",
                "value": HUMAN_TEMPLATE,
            },
        ],
    )
    
    print(f"Agent ID: {agent.id}")
    time.sleep(1) # Let db settle
    
    print("\n[Test 1] User supplies a name...")
    res = chat(client, agent.id, input="你好！我是张伟")
    
    tools_called = [s for s in res['sequence'] if s['type'] == 'tool_call']
    print(f"Tools explicitly invoked: {[t.get('content', {}).get('name', str(t)) for t in tools_called]}")
    
    if res['memory_diff'] and res['memory_diff']['old'] != res['memory_diff']['new']:
        print("✅ Memory successfully modified!")
        # Quick hack to show the diff on human roughly
        print(f"New Memory: {res['memory_diff']['new'].get('human', '')}")
    else:
        print("❌ FAILED: Memory was not modified via tool calls. Internal Reasoning:")
        reasoning = [s for s in res['sequence'] if s['type'] == 'reasoning']
        if reasoning: print(f"   > {reasoning[0]['content']}")
        
    print("\n[Test 2] User supplies a hobby...")
    res2 = chat(client, agent.id, input="我非常喜欢狗狗，你呢？")
    tools_called2 = [s for s in res2['sequence'] if s['type'] == 'tool_call']
    print(f"Tools explicitly invoked: {[t.get('content', {}).get('name', str(t)) for t in tools_called2]}")
    
    if res2['memory_diff'] and res2['memory_diff']['old'] != res2['memory_diff']['new']:
        print("✅ Memory successfully modified!")
        print(f"New Memory: {res2['memory_diff']['new'].get('human', '')}")
    else:
        print("❌ FAILED: Memory was not modified via tool calls. Internal Reasoning:")
        reasoning2 = [s for s in res2['sequence'] if s['type'] == 'reasoning']
        if reasoning2: print(f"   > {reasoning2[0]['content']}")
        
    # Cleanup to save DB space
    client.agents.delete(agent_id=agent.id)

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    
    test_prompt(CUSTOM_V1_PROMPT, "CUSTOM_V1_PROMPT")
    time.sleep(2)
    test_prompt(AGGRESSIVE_MEMORY_PROMPT, "AGGRESSIVE_MEMORY_PROMPT")
    time.sleep(2)
    test_prompt(STRUCTURED_MEMORY_PROMPT, "STRUCTURED_MEMORY_PROMPT")
    time.sleep(2)
    test_prompt(TOOLS_FIRST_PROMPT, "TOOLS_FIRST_PROMPT")