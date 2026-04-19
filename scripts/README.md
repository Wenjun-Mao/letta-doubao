# Utility Scripts

This folder contains various automation and diagnostic scripts for managing both your local development environment and the Letta server.

You should generally run these scripts from the **project root directory** (e.g., `letta-doubao/`), not from inside the `scripts/` folder.

## Scripts Overview

### Database Resets
Wipes all existing Letta memory/agents inside the PostgreSQL volume and fully restarts the Docker containers for a clean slate. Supports passing an env file argument (defaults to `.env`).

* **Windows (PowerShell):** `reset_database.ps1`
* **Linux / Ubuntu (Bash):** `reset_database.sh`

### Letta Configuration & Tools
* **`sync_tools.py`**: Connects to the running Letta server, pulls a list of *all* available tools, and generates `utils/letta_tools.py` for full IDE autocomplete and inline documentation. You should run this anytime a new tool is published.
* **`collect_diagnostics.sh`**: Collects Docker/Compose status, health checks, service logs, and connectivity probes into a timestamped diagnostics bundle. Designed for remote machine troubleshooting.
* **`seed_nltk_data.sh`**: Pre-downloads NLTK `punkt_tab` into `data/nltk_data` so Letta startup can use local NLTK data in restricted/offline networks.

### Testing Scripts Location
All test runners were moved to the `tests/` directory to keep responsibilities clear:
* `tests/runners/persona_guardrail_runner.py`
* `tests/runners/memory_update_runner.py`
* `tests/checks/provider_embedding_matrix_check.py`
* `tests/checks/prompt_strategy_check.py`
* `tests/checks/agent_bootstrap_check.py`

---

## 🚀 Quick Execution Commands

**Reset the Letta Database (Windows - PowerShell):**
```powershell
.\scripts\reset_database.ps1
```

**Reset with a specific env file (Windows - PowerShell):**
```powershell
.\scripts\reset_database.ps1 .env
```

**Reset the Letta Database (Ubuntu / Linux - Terminal):**
```bash
chmod +x scripts/reset_database.sh
./scripts/reset_database.sh
```

**Reset with a specific env file (Ubuntu / Linux - Terminal):**
```bash
chmod +x scripts/reset_database.sh
./scripts/reset_database.sh .env
```

**Sync Letta Tools for autocomplete:**
```bash
uv run scripts/sync_tools.py
```

**Collect diagnostics bundle (Ubuntu/Linux):**
```bash
chmod +x scripts/collect_diagnostics.sh
./scripts/collect_diagnostics.sh .env
```

**Pre-seed NLTK data for startup (Ubuntu/Linux):**
```bash
chmod +x scripts/seed_nltk_data.sh
./scripts/seed_nltk_data.sh
```

The script prints and saves the output bundle path, for example:

- `diagnostics/letta_diag_YYYYMMDD_HHMMSS/`
- `diagnostics/letta_diag_YYYYMMDD_HHMMSS.tar.gz`

**Run Agent Integration / Verification Test:**
```bash
uv run tests/checks/agent_bootstrap_check.py
```

**Run Provider + Embedding Matrix Test (27B only):**
```bash
uv run tests/checks/provider_embedding_matrix_check.py
```

**Run Provider + Embedding Matrix Test with custom handles:**
```bash
TEST_EMBEDDING_HANDLES="letta/letta-free,lmstudio_openai/text-embedding-qwen3-embedding-0.6b" uv run tests/checks/provider_embedding_matrix_check.py
```

**Run Conversation Suite (all suite configs):**
```bash
uv run tests/runners/persona_guardrail_runner.py
```

**Run Conversation Suite and force one embedding handle for all configs:**
```bash
uv run tests/runners/persona_guardrail_runner.py --config tests/configs/suites --embedding letta/letta-free
```

**Run Conversation Suite for a specific config file:**
```bash
uv run tests/runners/persona_guardrail_runner.py --config tests/configs/suites/lmstudio_chat_v20260418.json --embedding letta/letta-free
```

**Run Prompt Variant Comparison:**
```bash
uv run tests/checks/prompt_strategy_check.py
```

**Run Agent Platform API E2E Check:**
```bash
uv run tests/checks/platform_api_e2e_check.py
```

**Run ADE MVP Smoke E2E Check:**
```bash
uv run tests/checks/ade_mvp_smoke_e2e_check.py
```

**Run Platform Flag Gate Check:**
```bash
uv run tests/checks/platform_flag_gate_check.py
```

**Run Dual-Run Cutover Gate (backend E2E + ADE smoke):**
```bash
uv run tests/checks/platform_dual_run_gate.py
```

**Run Fresh-Agent Memory Update Rounds:**
```bash
uv run tests/runners/memory_update_runner.py --rounds 10 --model lmstudio_openai/gemma-4-31b-it --embedding letta/letta-free
```

**Start Letta with a specific env profile (example `.env`):**
```bash
LETTA_ENV_FILE=.env docker compose --profile ui up -d
```
