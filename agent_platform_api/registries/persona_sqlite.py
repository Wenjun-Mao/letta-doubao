from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_platform_api.registries.persona_exchange import (
    PersonaConflictPolicy,
    export_personas_jsonl,
    export_personas_markdown,
    import_personas_jsonl,
)
from agent_platform_api.registries.prompt_persona_store.codec import first_non_empty_line
from agent_platform_api.registries.prompt_persona_store.types import (
    KEY_PATTERN,
    KNOWN_SCENARIOS,
    RegistryError,
    ScenarioKind,
)


class PersonaSqliteRegistry:
    """SQLite-backed persona library with JSONL/Markdown exchange helpers."""

    def __init__(
        self,
        project_root: Path,
        *,
        db_path: Path | None = None,
        seed_jsonl_path: Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.db_path = (db_path or self.project_root / "data" / "personas" / "personas.sqlite3").resolve()
        self.seed_jsonl_path = (
            seed_jsonl_path or self.project_root / "agent_platform_api" / "seed_data" / "personas.jsonl"
        ).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._seed_if_empty()

    def list_personas(
        self,
        *,
        include_archived: bool = False,
        scenario: ScenarioKind | None = None,
        search: str = "",
    ) -> list[dict[str, Any]]:
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        if resolved_scenario == "label":
            return []
        cleaned_search = str(search or "").strip()
        if cleaned_search:
            return self.search_personas(
                cleaned_search,
                include_archived=include_archived,
                scenario=resolved_scenario,
            )

        clauses: list[str] = []
        params: list[Any] = []
        if not include_archived:
            clauses.append("archived = 0")
        if resolved_scenario:
            clauses.append("scenario = ?")
            params.append(resolved_scenario)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM personas {where_sql} ORDER BY archived ASC, scenario ASC, key ASC",
                params,
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def search_personas(
        self,
        query: str,
        *,
        include_archived: bool = False,
        scenario: ScenarioKind | None = None,
    ) -> list[dict[str, Any]]:
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        if resolved_scenario == "label":
            return []
        cleaned_query = str(query or "").strip()
        if not cleaned_query:
            return self.list_personas(include_archived=include_archived, scenario=resolved_scenario)

        clauses = ["persona_fts MATCH ?"]
        params: list[Any] = [self._fts_query(cleaned_query)]
        if not include_archived:
            clauses.append("p.archived = 0")
        if resolved_scenario:
            clauses.append("p.scenario = ?")
            params.append(resolved_scenario)
        where_sql = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT p.*
                FROM persona_fts f
                JOIN personas p ON p.id = f.persona_id
                WHERE {where_sql}
                ORDER BY rank, p.archived ASC, p.scenario ASC, p.key ASC
                """,
                params,
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_persona(
        self,
        key: str,
        *,
        archived: bool = False,
        scenario: ScenarioKind | None = None,
    ) -> dict[str, Any] | None:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        if resolved_scenario == "label":
            return None

        clauses = ["key = ?", "archived = ?"]
        params: list[Any] = [normalized, 1 if archived else 0]
        if resolved_scenario:
            clauses.append("scenario = ?")
            params.append(resolved_scenario)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM personas WHERE {' AND '.join(clauses)}",
                params,
            ).fetchone()
        return self._row_to_record(row) if row else None

    def create_persona(
        self,
        *,
        key: str,
        content: str,
        label: str | None = None,
        description: str | None = None,
        scenario: ScenarioKind | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True) or self._infer_scenario_from_key(normalized)
        self._ensure_supported_scenario(resolved_scenario)
        self._validate_key_scenario(normalized, resolved_scenario)
        if not str(content or "").strip():
            raise RegistryError("content is required")

        now = self._now()
        with self._connect() as conn:
            existing = conn.execute("SELECT key FROM personas WHERE key = ?", (normalized,)).fetchone()
            if existing:
                raise RegistryError(f"persona '{normalized}' already exists")
            cursor = conn.execute(
                """
                INSERT INTO personas
                    (key, scenario, label, description, content, tags_json, metadata_json, archived, created_at, updated_at, archived_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL)
                """,
                (
                    normalized,
                    resolved_scenario,
                    str(label or "").strip(),
                    str(description or "").strip(),
                    str(content),
                    self._json_list(tags or []),
                    self._json_object(metadata or {}),
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM personas WHERE id = ?", (cursor.lastrowid,)).fetchone()
            self._upsert_fts(conn, row)
        return self._row_to_record(row)

    def update_persona(
        self,
        *,
        key: str,
        content: str | None = None,
        label: str | None = None,
        description: str | None = None,
        scenario: ScenarioKind | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        self._ensure_supported_scenario(resolved_scenario)
        existing = self.get_persona(normalized, archived=False, scenario=resolved_scenario)
        if not existing:
            raise RegistryError(f"persona '{normalized}' not found")

        next_content = str(existing.get("content", "") if content is None else content)
        if not next_content.strip():
            raise RegistryError("content is required")
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE personas
                SET label = ?,
                    description = ?,
                    content = ?,
                    tags_json = ?,
                    metadata_json = ?,
                    updated_at = ?
                WHERE key = ? AND archived = 0
                """,
                (
                    str(existing.get("label", "") if label is None else label).strip(),
                    str(existing.get("description", "") if description is None else description).strip(),
                    next_content,
                    self._json_list(existing.get("tags", []) if tags is None else tags),
                    self._json_object(existing.get("metadata", {}) if metadata is None else metadata),
                    now,
                    normalized,
                ),
            )
            row = conn.execute("SELECT * FROM personas WHERE key = ?", (normalized,)).fetchone()
            self._upsert_fts(conn, row)
        return self._row_to_record(row)

    def archive_persona(self, key: str, scenario: ScenarioKind | None = None) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        self._ensure_supported_scenario(resolved_scenario)
        existing = self.get_persona(normalized, archived=False, scenario=resolved_scenario)
        if not existing:
            raise RegistryError(f"persona '{normalized}' not found")
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE personas SET archived = 1, archived_at = ?, updated_at = ? WHERE key = ?",
                (now, now, normalized),
            )
            row = conn.execute("SELECT * FROM personas WHERE key = ?", (normalized,)).fetchone()
            self._upsert_fts(conn, row)
        return self._row_to_record(row)

    def restore_persona(self, key: str, scenario: ScenarioKind | None = None) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        self._ensure_supported_scenario(resolved_scenario)
        existing = self.get_persona(normalized, archived=True, scenario=resolved_scenario)
        if not existing:
            raise RegistryError(f"Archived persona '{normalized}' not found")
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE personas SET archived = 0, archived_at = NULL, updated_at = ? WHERE key = ?",
                (now, normalized),
            )
            row = conn.execute("SELECT * FROM personas WHERE key = ?", (normalized,)).fetchone()
            self._upsert_fts(conn, row)
        return self._row_to_record(row)

    def purge_persona(self, key: str, scenario: ScenarioKind | None = None) -> None:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        self._ensure_supported_scenario(resolved_scenario)
        existing = self.get_persona(normalized, archived=True, scenario=resolved_scenario)
        if not existing:
            raise RegistryError(f"Archived persona '{normalized}' not found")
        persona_id = int(existing["id"])
        with self._connect() as conn:
            conn.execute("DELETE FROM persona_fts WHERE persona_id = ?", (persona_id,))
            conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))

    def import_jsonl(self, path: Path, *, on_conflict: PersonaConflictPolicy = "error") -> dict[str, int]:
        return import_personas_jsonl(self, path, on_conflict=on_conflict)

    def export_jsonl(
        self,
        path: Path,
        *,
        include_archived: bool = False,
        scenario: ScenarioKind | None = None,
    ) -> int:
        return export_personas_jsonl(self, path, include_archived=include_archived, scenario=scenario)

    def export_markdown(
        self,
        path: Path,
        *,
        include_archived: bool = False,
        scenario: ScenarioKind | None = None,
    ) -> int:
        return export_personas_markdown(self, path, include_archived=include_archived, scenario=scenario)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS personas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    scenario TEXT NOT NULL CHECK (scenario IN ('chat', 'comment')),
                    label TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_personas_scenario_archived_key
                    ON personas (scenario, archived, key);
                CREATE VIRTUAL TABLE IF NOT EXISTS persona_fts
                    USING fts5(key, label, description, content, tags, persona_id UNINDEXED);
                """
            )

    def _seed_if_empty(self) -> None:
        with self._connect() as conn:
            count = int(conn.execute("SELECT COUNT(*) FROM personas").fetchone()[0])
        if count == 0 and self.seed_jsonl_path.is_file():
            self.import_jsonl(self.seed_jsonl_path, on_conflict="skip")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _upsert_fts(self, conn: sqlite3.Connection, row: sqlite3.Row) -> None:
        record = self._row_to_record(row)
        persona_id = int(record["id"])
        conn.execute("DELETE FROM persona_fts WHERE persona_id = ?", (persona_id,))
        conn.execute(
            """
            INSERT INTO persona_fts (key, label, description, content, tags, persona_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record["key"],
                record["label"],
                record["description"],
                record["content"],
                " ".join(record.get("tags", [])),
                persona_id,
            ),
        )

    def _row_to_record(self, row: sqlite3.Row) -> dict[str, Any]:
        tags = self._loads_json(row["tags_json"], [])
        metadata = self._loads_json(row["metadata_json"], {})
        content = str(row["content"] or "")
        return {
            "id": int(row["id"]),
            "kind": "persona",
            "scenario": str(row["scenario"] or "chat"),
            "key": str(row["key"] or ""),
            "label": str(row["label"] or ""),
            "description": str(row["description"] or ""),
            "content": content,
            "preview": first_non_empty_line(content)[:180],
            "length": len(content),
            "archived": bool(row["archived"]),
            "archived_at": row["archived_at"],
            "source_path": f"{self._relative_db_path()}#{row['key']}",
            "updated_at": str(row["updated_at"] or ""),
            "output_schema": None,
            "tags": tags if isinstance(tags, list) else [],
            "metadata": metadata if isinstance(metadata, dict) else {},
        }

    def _relative_db_path(self) -> str:
        try:
            return self.db_path.relative_to(self.project_root).as_posix()
        except ValueError:
            return self.db_path.as_posix()

    def _normalize_key(self, key: str) -> str:
        normalized = str(key or "").strip().lower()
        if not KEY_PATTERN.fullmatch(normalized):
            raise RegistryError(
                "Invalid key. Use 2-64 chars with lowercase letters, numbers, underscores, or hyphens; must start with a letter."
            )
        return normalized

    def _normalize_scenario(self, scenario: str | None, allow_none: bool = False) -> ScenarioKind | None:
        if scenario is None:
            return None if allow_none else "chat"
        normalized = str(scenario or "").strip().lower()
        if not normalized:
            return None if allow_none else "chat"
        if normalized not in KNOWN_SCENARIOS:
            raise RegistryError(f"Unsupported scenario: {scenario}")
        return normalized  # type: ignore[return-value]

    def _infer_scenario_from_key(self, key: str) -> ScenarioKind:
        normalized = self._normalize_key(key)
        if normalized.startswith("label_"):
            raise RegistryError("Label scenario does not support persona templates.")
        if normalized.startswith("comment_"):
            return "comment"
        if normalized.startswith("chat_"):
            return "chat"
        raise RegistryError("Unable to infer scenario from key. Prefix persona keys with 'chat_' or 'comment_'.")

    def _validate_key_scenario(self, key: str, scenario: ScenarioKind) -> None:
        required_prefix = f"{scenario}_"
        if not key.startswith(required_prefix):
            raise RegistryError(f"Key '{key}' must start with '{required_prefix}' for scenario '{scenario}'.")

    @staticmethod
    def _ensure_supported_scenario(scenario: ScenarioKind | None) -> None:
        if scenario == "label":
            raise RegistryError("Label scenario does not support persona templates.")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _json_list(value: list[Any]) -> str:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return json.dumps(cleaned, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _json_object(value: dict[str, Any]) -> str:
        return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _loads_json(raw: str, default: Any) -> Any:
        try:
            return json.loads(str(raw or ""))
        except json.JSONDecodeError:
            return default

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = [term.strip().replace('"', '""') for term in str(query or "").split() if term.strip()]
        if not terms:
            cleaned = str(query or "").strip().replace('"', '""')
            return f'"{cleaned}"'
        return " ".join(f'"{term}"' for term in terms)
