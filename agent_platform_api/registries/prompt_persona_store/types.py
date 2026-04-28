from __future__ import annotations

import re
from typing import Literal

TemplateKind = Literal["prompt", "persona"]
ScenarioKind = Literal["chat", "comment", "label"]

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
KNOWN_SCENARIOS: tuple[ScenarioKind, ...] = ("chat", "comment", "label")

META_LABEL = "LABEL"
META_DESCRIPTION = "DESCRIPTION"
PROMPT_VAR = "PROMPT"
PERSONA_VAR = "PERSONA_TEXT"
OUTPUT_SCHEMA_VAR = "OUTPUT_SCHEMA"


class RegistryError(ValueError):
    """Raised when prompt/persona registry operations fail."""
