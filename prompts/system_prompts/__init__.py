from .custom_v1 import PROMPT as CUSTOM_V1_PROMPT
from .custom_v1_aggressive_memory import PROMPT as AGGRESSIVE_MEMORY_PROMPT
from .custom_v1_structured_memory import PROMPT as STRUCTURED_MEMORY_PROMPT
from .custom_v1_tools_first import PROMPT as TOOLS_FIRST_PROMPT
from .memgpt_v2_chat import PROMPT as MEMGPT_V2_CHAT_PROMPT

__all__ = [
	"CUSTOM_V1_PROMPT",
	"AGGRESSIVE_MEMORY_PROMPT",
	"STRUCTURED_MEMORY_PROMPT",
	"TOOLS_FIRST_PROMPT",
	"MEMGPT_V2_CHAT_PROMPT",
]
