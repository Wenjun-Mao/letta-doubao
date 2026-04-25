# Utility Scripts

This folder contains various automation and diagnostic scripts for managing both your local development environment and the Letta server.

You should generally run these scripts from the **project root directory**, not from inside the `scripts/` folder.

## Scripts Overview

### Database Resets
Wipes all existing Letta memory/agents inside the PostgreSQL volume and fully restarts the Docker containers for a clean slate. Supports passing an env file argument (defaults to `.env`).

* **Windows (PowerShell):** `reset_database.ps1`
* **Linux / Ubuntu (Bash):** `reset_database.sh`

### Letta Configuration & Tools
* **`sync_tools.py`**: Connects to the running Letta server, pulls a list of *all* available tools, and regenerates `agent_platform_api/letta/tools.py` for IDE autocomplete and inline documentation. You should run this anytime a new tool is published.
* **`collect_diagnostics.sh`**: Collects Docker/Compose status, health checks, service logs, and connectivity probes into a timestamped diagnostics bundle. Designed for remote machine troubleshooting.
* **`seed_nltk_data.sh`**: Pre-downloads NLTK `punkt_tab` into `data/nltk_data` so Letta startup can use local NLTK data in restricted/offline networks.
* **`probe_provider_models.py`**: Re-runs provider chat probes, currently used to regenerate the persisted Ark allowlist at `agent_platform_api/catalog_data/ark_chat_probe_report.json`.

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

**Run Agent Platform API E2E Check:**
```bash
uv run python tests/checks/platform_api_e2e_check.py
```

**Run ADE MVP Smoke E2E Check:**
```bash
uv run python tests/checks/ade_mvp_smoke_e2e_check.py
```

**Run full pytest coverage:**
```bash
uv run python -m pytest
```

**Regenerate the persisted Ark allowlist:**
```bash
uv run python scripts/probe_provider_models.py --source-id ark --mode chat-probe --write
```

**Start Letta with a specific env profile (example `.env`):**
```bash
LETTA_ENV_FILE=.env docker compose --profile ui up -d
```
