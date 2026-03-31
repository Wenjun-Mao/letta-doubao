import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    from letta_client import Letta
    import dotenv
    dotenv.load_dotenv(override=True)
    return Letta, mo


@app.cell
def _(mo):
    mo.md("""
    # 3. Inner Workings & Tool Calling Dynamics
    This notebook addresses **Question 5**.
    """)
    return


@app.cell
def _(Letta):
    client = Letta(base_url="http://localhost:8283")
    agents = list(client.agents.list())
    agent_id = agents[-1].id if agents else None
    return agent_id, client


@app.cell
def _(agent_id, client):
    print("Test message setup ready. (Note: Run this locally if Letta server is fully connected).")
    try:
        response = client.agents.messages.create(
            agent_id=agent_id,
            messages=[{"role": "user", "content": "Hi there! My name is John. How are you doing today?"}]
        )
        print("\nSuccess! Response captured.")
    except Exception as e:
        print(f"Could not generate response, possibly model disconnected:\n{e}")
        response = None
    return (response,)


@app.cell
def _(mo):
    mo.md("""
    ### Analyzing the internal loop (Message Queue)
    """)
    return


@app.cell
def _(response):
    print("=== Execution Pipeline Sequence ===\n")
    if response and hasattr(response, 'messages'):
        for m in response.messages:
            m_data = m.model_dump() if hasattr(m, "model_dump") else m
            m_type = m_data.get("message_type")

            if m_type == "user_message": print(f"[USER SAYS] '{m_data.get('content')}'")
            elif m_type == "reasoning_message": print(f"      [LLM INTERNAL THOUGHT] '{str(m_data.get('reasoning')).strip()[:100]}...'")
            elif m_type == "tool_call_message":
                tool_call = m_data.get("tool_call", {})
                if hasattr(tool_call, 'model_dump'): tool_call = tool_call.model_dump()
                print(f"      [LLM TOOL INVOCATION] Invoked `{tool_call.get('name')}` with arguments: {str(tool_call.get('arguments'))[:50]}...")
            elif m_type == "tool_return_message": print(f"      [OS TOOL RESULT] Status: {str(m_data.get('tool_return'))[:60]}...")
            elif m_type == "assistant_message": print(f"[AGENT REPLIES] '{m_data.get('content')}'")
            else: print(f"[OTHER MESSAGE] TYPE: {m_type}")
    else: print("No response object to analyze.")
    return


if __name__ == "__main__":
    app.run()
