from letta_client import Letta

def get_agent_system_message(
    agent_id: str,
    client=None,
    print_out: bool = True
):
    """
    Fetches the initially compiled System Message payload for an agent.
    This shows exactly what the LLM receives, including injected memory blocks.
    """
    if client is None:
        client = Letta(base_url="http://localhost:8283")
        
    messages = list(client.agents.messages.list(agent_id=agent_id))
    
    # The first message in the history is always the compiled system prompt
    system_msg = None
    for msg in messages:
        if getattr(msg, "role", "") == "system" or getattr(msg, "message_type", "") == "system_message":
            system_msg = msg
            break
            
    if not system_msg:
        print("No system message found in the agent's history.")
        return None
        
    content = system_msg.content
    if isinstance(content, list):
        content = content[0].text if hasattr(content[0], 'text') else str(content[0])

    if print_out:
        print("=== Compiled System Message Payload ===")
        print(content)
        
    return content

def get_agent_tools(
    agent_id,
    client=None,
    print_out=True
):
    if client is None:
        client = Letta(base_url="http://localhost:8283")
    agent = client.agents.retrieve(
        agent_id=agent_id,
    )

    # Fetch the list of tools attached to this specific agent
    tools_raw = list(client.agents.tools.list(agent_id=agent.id))

    # Letta backend sometimes returns duplicates (e.g. tools attached via blocks and base agent)
    # We can deduplicate them by tool ID:
    tools = list({t.id: t for t in tools_raw}.values())

    if print_out:
        print(f"=== Agent Tools ({len(tools)}) ===")
        # print out tool names first
        for tool in tools:
            print(f"- {tool.name}")

        print("\n=== Agent Tools with Descriptions ===")

        for tool in tools:
            print(f"- {tool.name}: {tool.description}")

    return tools

def get_tool_id_by_name(tool_name: str, client=None) -> str:
    """
    Dynamically finds a tool's ID by its name to avoid hardcoding UUIDs.
    """
    if client is None:
        client = Letta(base_url="http://localhost:8283")
        
    for tool in client.tools.list():
        if tool.name == tool_name:
            return tool.id
            
    raise ValueError(f"Tool with name '{tool_name}' not found.")


