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
    # 2. System Instructions and Tools
    This notebook addresses **Question 4**.
    """)
    return


@app.cell
def _(Letta):
    client = Letta(base_url="http://localhost:8283")
    agents = list(client.agents.list())
    agent_state = client.agents.retrieve(agents[-1].id) if len(agents) > 0 else None
    return agent_state, client


@app.cell
def _(mo):
    mo.md("""
    ### Agent System Instructions
    """)
    return


@app.cell
def _(agent_state):
    print("=== Core System Instructions ===\n")
    if agent_state:
        # print(agent_state.system[:1500] + "\n... [CONT.] ...")
        print(agent_state.system)
    return


@app.cell
def _(mo):
    mo.md("""
    ### Agent Tools
    Letta natively binds basic memory management tools.
    """)
    return


@app.cell
def _(agent_state, client):
    print("=== Tools Attached to this Agent ===\n")
    if agent_state:
        # Tools are lazy-loaded, fetch from their endpoint
        tools = list(client.agents.tools.list(agent_id=agent_state.id))
        for t in tools:
            # print(f"- {t.name} : {str(t.description)[:80]}...")
            print(f"- {t.name} : {str(t.description)}")
    return


@app.cell
def _(mo):
    mo.md("""
    ### How to modify the Agent's Rules
    System instructions can be updated via `client.agents.update(agent_id, system=...)`
    """)
    return


@app.cell
def _():
    print("System instructions can be updated dynamically!")
    return


if __name__ == "__main__":
    app.run()
