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
    # 1. Letta Agents and Memory
    This notebook addresses **Questions 1, 2, and 3**.
    Here we will:
    1. Show all the agents you've created.
    2. Explore Letta "Models" and server settings (since User IDs / Identities are managed silently via Entity/Projects in newer versions).
    3. Dive into the actual "Core Memory" (Working Context) of an individual agent by fetching its Memory Blocks.
    """)
    return


@app.cell
def _(Letta):
    client = Letta(base_url="http://localhost:8283")
    agents = list(client.agents.list())

    print(f"=== Total Agents Created: {len(agents)} ===")
    for a in agents:
        print(f"- {a.name} (ID: {a.id})")
    return agents, client


@app.cell
def _(mo):
    mo.md("""
    ### Server Models
    Instead of identities (which are abstracted away), let's look at the Models Letta is currently wired to interact with.
    """)
    return


@app.cell
def _(client):
    print("=== Letta Registered Models ===")
    try:
        models = list(client.models.list())
        if not models: print("No explicitly defined models found.")
        for m in models: print(f"Model ID: {m.handle}")
    except Exception as e: print(f"Could not list models: {e}")
    return


@app.cell
def _(mo):
    mo.md("""
    ### Diving into Agent Memory Blocks
    In MemGPT terms, 'Working Context' is synonymous with **Core Memory**.
    In the Letta API, memory blocks are lazy-loaded, so we fetch them explicitly from `client.agents.blocks`.
    """)
    return


@app.cell
def _(agents):
    test_agent_id1 = agents[-1].id if agents else None
    print(f"Using Agent ID: {test_agent_id1}")
    return


@app.cell
def _(agents, client):
    for agent in agents:
        print(f"Agent Name: {agent.name}, ID: {agent.id}")
        test_agent_id = agent.id
        if test_agent_id:
            agent_state = client.agents.retrieve(test_agent_id)
            print(f"=== Memory Blocks for Agent: {agent_state.name} ===\n")
            blocks_data = list(client.agents.blocks.list(agent_id=test_agent_id))
            if not blocks_data: print("No memory blocks configured for this agent.")
            for block in blocks_data:
                print(f"---- Block [{block.label}] ----")
                print(f"{block.value}\n")
            print("="*50)
            print("\n\n")
        else:
            print("No agents found.")
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
