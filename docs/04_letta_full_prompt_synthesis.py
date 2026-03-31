import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    from letta_client import Letta

    return Letta, mo


@app.cell
def _(mo):
    mo.md("""
    # 4. The MemGPT 'Full Prompt' Making Process
    This final notebook captures **Question 6**.
    """)
    return


@app.cell
def _(Letta):
    client = Letta(base_url="http://localhost:8283")
    agents = list(client.agents.list())
    agent = client.agents.retrieve(agents[-1].id) if len(agents) > 0 else None
    messages = list(client.agents.messages.list(agent_id=agent.id, limit=5)) if agent else []
    return agent, client, messages


@app.cell
def _(mo):
    mo.md("""
    ### Section 1: The Hardcoded System Prompt
    """)
    return


@app.cell
def _(agent):
    if agent: print(f"System Command Size: {len(agent.system)} characters.\n")
    return


@app.cell
def _(mo):
    mo.md("""
    ### Section 2: Working Context (The Injection)
    """)
    return


@app.cell
def _(agent, client):
    print("=== System Working Context Injection ===\n")
    context_string = ""
    if agent:
        blocks = list(client.agents.blocks.list(agent_id=agent.id))
        for block in blocks:
            context_string += f"<{block.label}>\n{block.value}\n</{block.label}>\n\n"
        print(context_string)
    return


@app.cell
def _(mo):
    mo.md("""
    ### Section 3: The FIFO Queue (Sliding Window)
    """)
    return


@app.cell
def _(messages):
    print(f"=== Messages Window ===\n")
    print(f"Loaded the last {len(messages)} chronological messages in the immediate payload.")
    for msg in reversed(messages):
        m_data = msg.model_dump() if hasattr(msg, "model_dump") else msg
        role = "user" if m_data.get("message_type") == "user_message" else "assistant"
        content_val = str(m_data.get("content"))[:60].strip() if m_data.get("content") else "<Tool Exec/Thought>"
        print(f"{role.upper()}: {content_val}...")
    return


@app.cell
def _(mo):
    mo.md("""
    ### The Final Synthesis Payload
    If you manually ran a request, the payload matches exactly these three sections merged into standard JSON.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
 
    """)
    return


if __name__ == "__main__":
    app.run()
