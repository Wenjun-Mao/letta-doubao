from __future__ import annotations

from typing import Literal

ScenarioType = Literal["chat", "comment", "label"]
CommentingTaskShape = Literal["classic", "all_in_system", "structured_output"]
LabelingOutputMode = Literal["strict_json_schema", "json_schema", "best_effort_prompt_json"]
