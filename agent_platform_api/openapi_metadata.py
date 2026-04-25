from __future__ import annotations

TAG_AGENT_STUDIO = "Agent Studio"
TAG_COMMENT_LAB = "Comment Lab"
TAG_LABEL_LAB = "Label Lab"
TAG_PLATFORM_CONTROL = "Platform Control"
TAG_PLATFORM_META = "Platform Meta"
TAG_PLATFORM_RUNTIME = "Platform Runtime"
TAG_PROMPT_CENTER = "Prompt Center"
TAG_SCHEMA_CENTER = "Schema Center"
TAG_TOOL_CENTER = "Tool Center"
TAG_TEST_CENTER = "Test Center"

OPENAPI_TAGS = [
    {
        "name": TAG_AGENT_STUDIO,
        "description": "Persistent-agent creation, inspection, and chat operations.",
    },
    {
        "name": TAG_COMMENT_LAB,
        "description": "Stateless comment generation using router-visible models.",
    },
    {
        "name": TAG_LABEL_LAB,
        "description": "Stateless grouped entity extraction using Label Lab schemas.",
    },
    {
        "name": TAG_PROMPT_CENTER,
        "description": "File-backed prompt and persona template management.",
    },
    {
        "name": TAG_SCHEMA_CENTER,
        "description": "File-backed Label Lab JSON schema management.",
    },
    {
        "name": TAG_TOOL_CENTER,
        "description": "Tool discovery, Tool Center CRUD, and tool attach/detach operations.",
    },
    {
        "name": TAG_TEST_CENTER,
        "description": "Orchestrated live checks and test-run artifact access.",
    },
    {
        "name": TAG_PLATFORM_RUNTIME,
        "description": "Low-level runtime message endpoints with optional overrides.",
    },
    {
        "name": TAG_PLATFORM_CONTROL,
        "description": "Persistent agent lifecycle and configuration control endpoints.",
    },
    {
        "name": TAG_PLATFORM_META,
        "description": "Platform capabilities, model catalog diagnostics, and shared runtime options.",
    },
]
