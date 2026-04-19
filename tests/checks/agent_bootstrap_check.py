import os
import sys
import argparse

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from letta_client import Letta
from prompts.persona import PERSONAS, HUMAN_TEMPLATE
from prompts.system_prompts import CUSTOM_V2_PROMPT
from tests.shared.config_defaults import (
    DEFAULT_EMBEDDING_HANDLE,
    DEFAULT_LETTA_BASE_URL,
    DEFAULT_TEST_MODEL_HANDLE,
)

def run_verification(*, model_handle: str, embedding_handle: str):
    client = Letta(base_url=DEFAULT_LETTA_BASE_URL)
    
    print("--- CREATING AGENT ---")
    agent = client.agents.create(
        name="test-verification-agent",
        system=CUSTOM_V2_PROMPT,
        model=model_handle,
        embedding=embedding_handle,
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
    
    print(f"Created agent with ID: {agent.id}")
    
    print("\n\n--- 1. VERIFY DESCRIPTIONS ARE AUTO-FILLED ---")
    blocks = agent.blocks if hasattr(agent, "blocks") else getattr(agent.memory, "blocks", [])
    for block in blocks:
        print(f"Block [{block.label}] description:")
        print(f"  {block.description}")
        print()
        
    print("\n\n--- 2. VERIFY DESCRIPTIONS ARE IN THE SYSTEM PROMPT ---")
    system_prompt = agent.system
    print("Excerpt from the compiled system prompt:")
    start_idx = system_prompt.find("<memory_blocks>")
    if start_idx != -1:
        end_idx = system_prompt.find("</memory_blocks>", start_idx)
        if end_idx == -1: end_idx = start_idx + 1500
        print(system_prompt[start_idx:end_idx+16])
    else:
        print("Could not find <memory_blocks> in the system prompt. Printing full system prompt:")
        print(system_prompt)
        
    print("\n\n--- 3. VERIFY DEFAULT EMBEDDING IS USED ---")
    print(f"Embedding snippet from agent instance:")
    if hasattr(agent, "embedding"):
        print(f"  agent.embedding: {agent.embedding}")
    if hasattr(agent, "embedding_config"):
        print(f"  agent.embedding_config: {agent.embedding_config}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate agent bootstrap memory block descriptions and defaults")
    parser.add_argument(
        "--model",
        default=DEFAULT_TEST_MODEL_HANDLE,
        help="Model handle used for agent creation.",
    )
    parser.add_argument(
        "--embedding",
        default=DEFAULT_EMBEDDING_HANDLE,
        help="Embedding handle used for agent creation.",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = _parse_args()
    run_verification(model_handle=str(args.model), embedding_handle=str(args.embedding))
    