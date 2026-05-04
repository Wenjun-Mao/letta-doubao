# Development Conventions

This repo favors boring, discoverable structure over clever scattering. If a future change makes you ask "where is the rest of this?", colocate the related pieces.

## Config Boundaries

- Root `config/` is reserved for application/runtime source-of-truth config.
- Workflow-specific config belongs beside the workflow runner.
- Current root config should stay limited to project-wide runtime inputs such as `config/model_router_sources.json` and `config/model_router_model_profiles.json`.

## Workflow And Eval Folders

Use `evals/<workflow_name>/` for evaluation, probe, benchmark, or research workflows that have their own runner/config/input/output lifecycle.

Each workflow should include:

- `README.md` with purpose, smoke/full commands, config fields, outputs, and troubleshooting.
- `run.py` or another obvious entrypoint.
- `config.toml` if the workflow is configurable.
- `inputs/` for checked-in sample input when useful.
- `outputs/` for generated artifacts, ignored by git.

Avoid compatibility shims for newly introduced workflow paths unless explicitly requested.

## Scripts Folder

Keep `scripts/` for repo-wide utilities without workflow-specific config/output bundles, such as diagnostics, OpenAPI export, reset helpers, seed helpers, or small maintenance commands.

If a script grows a config file, sample input, and generated outputs, promote it into `evals/` or another named workflow folder.

## Documentation Expectations

When adding a workflow, update:

- The workflow-local `README.md`.
- `docs/codebase-map.md` when it changes where humans should look.
- Root README or MANUAL only when the workflow is part of normal development or operations.
