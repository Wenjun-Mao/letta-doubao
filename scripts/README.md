# Utility Scripts

This folder contains various automation and diagnostic scripts for managing both your local development environment and the Letta server.

You should generally run these scripts from the **project root directory** (e.g., `letta-doubao/`), not from inside the `scripts/` folder.

## Scripts Overview

### Database Resets
Wipes all existing Letta memory/agents inside the PostgreSQL volume and fully restarts the Docker containers for a clean slate. Supports passing an env file argument (defaults to `.env2`).

* **Windows (PowerShell):** `reset_database.ps1`
* **Linux / Ubuntu (Bash):** `reset_database.sh`

### Letta Configuration & Tools
* **`sync_tools.py`**: Connects to the running Letta server, pulls a list of *all* available tools, and generates `utils/letta_tools.py` for full IDE autocomplete and inline documentation. You should run this anytime a new tool is published.
* **`verify_agent.py`**: A diagnostic smoke-test script. Creates a test Chinese-speaking agent (Lin Xiao Tang) and pulls back its fully compiled internal `SystemMessage` format and attached blocks to verify DB formatting constraints.
* **`test_provider_embedding_matrix.py`**: Runs an end-to-end provider/embedding compatibility sweep (UI options endpoint, 27B model + selected embedding handles, Doubao handle checks) and prints a JSON report. Defaults to `letta/letta-free` only to reduce local VRAM pressure.
* **`run_conversation_suite.py`**: Runs config-driven multi-turn dialogue suites and writes one result file per config (including before/after `human` memory and all assistant replies).

---

## 🚀 Quick Execution Commands

**Reset the Letta Database (Windows - PowerShell):**
```powershell
.\scripts\reset_database.ps1
```

**Reset with a specific env file (Windows - PowerShell):**
```powershell
.\scripts\reset_database.ps1 .env3
```

**Reset the Letta Database (Ubuntu / Linux - Terminal):**
```bash
chmod +x scripts/reset_database.sh
./scripts/reset_database.sh
```

**Reset with a specific env file (Ubuntu / Linux - Terminal):**
```bash
chmod +x scripts/reset_database.sh
./scripts/reset_database.sh .env3
```

**Sync Letta Tools for autocomplete:**
```bash
uv run scripts/sync_tools.py
```

**Run Agent Integration / Verification Test:**
```bash
uv run scripts/verify_agent.py
```

**Run Provider + Embedding Matrix Test (27B only):**
```bash
uv run scripts/test_provider_embedding_matrix.py
```

**Run Provider + Embedding Matrix Test with custom handles:**
```bash
TEST_EMBEDDING_HANDLES="letta/letta-free,lmstudio_openai/text-embedding-qwen3-embedding-0.6b" uv run scripts/test_provider_embedding_matrix.py
```

**Run Conversation Suite (all suite configs):**
```bash
uv run scripts/run_conversation_suite.py
```

**Run Conversation Suite and force one embedding handle for all configs:**
```bash
uv run scripts/run_conversation_suite.py --config tests/configs/suites --embedding letta/letta-free
```

**Run Conversation Suite for a specific config file:**
```bash
uv run scripts/run_conversation_suite.py --config tests/configs/suites/qwen27_custom_v1.json
```

**Start Letta with a specific env profile (example `.env3`):**
```bash
LETTA_ENV_FILE=.env3 docker compose --profile ui up -d
```
