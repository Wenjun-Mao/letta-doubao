from __future__ import annotations

from agent_platform_api.options.builder import runtime_options
from agent_platform_api.options.catalog import enriched_catalog_items, invalidate_options_cache, model_catalog
from agent_platform_api.options.constants import (
    DEFAULT_CHAT_PERSONA_KEY,
    DEFAULT_CHAT_PROMPT_KEY,
    DEFAULT_COMMENT_PERSONA_KEY,
    DEFAULT_COMMENT_PROMPT_KEY,
    DEFAULT_EMBEDDING,
    DEFAULT_LABEL_PROMPT_KEY,
    DEFAULT_MODEL,
    MODEL_OPTION_OVERRIDES,
    MODEL_OPTION_PRIORITY,
    PREFERRED_EMBEDDING_OPTIONS,
    PROVIDER_MODEL_OPTION_OVERRIDES,
    PROVIDER_MODEL_OPTION_PRIORITY,
    SCENARIO_DEFAULTS,
)
from agent_platform_api.options.label_schemas import (
    active_label_schema_records,
    label_schema_option_entries,
    label_schema_record_map,
    resolve_default_label_schema_key,
)
from agent_platform_api.options.runtime_defaults import commenting_runtime_defaults, labeling_runtime_defaults
from agent_platform_api.options.selection import resolve_comment_model_selection, resolve_label_model_selection
from agent_platform_api.options.utils import dedupe_options

__all__ = [
    "DEFAULT_CHAT_PERSONA_KEY",
    "DEFAULT_CHAT_PROMPT_KEY",
    "DEFAULT_COMMENT_PERSONA_KEY",
    "DEFAULT_COMMENT_PROMPT_KEY",
    "DEFAULT_EMBEDDING",
    "DEFAULT_LABEL_PROMPT_KEY",
    "DEFAULT_MODEL",
    "MODEL_OPTION_OVERRIDES",
    "MODEL_OPTION_PRIORITY",
    "PREFERRED_EMBEDDING_OPTIONS",
    "PROVIDER_MODEL_OPTION_OVERRIDES",
    "PROVIDER_MODEL_OPTION_PRIORITY",
    "SCENARIO_DEFAULTS",
    "active_label_schema_records",
    "commenting_runtime_defaults",
    "dedupe_options",
    "enriched_catalog_items",
    "invalidate_options_cache",
    "label_schema_option_entries",
    "label_schema_record_map",
    "labeling_runtime_defaults",
    "model_catalog",
    "resolve_comment_model_selection",
    "resolve_default_label_schema_key",
    "resolve_label_model_selection",
    "runtime_options",
]
