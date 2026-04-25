"""
Auto-generated Tool Registry.
Run `uv run scripts/sync_tools.py` to rebuild this file if you add custom tools to Letta.
"""

class DefaultTools:
    """
    Letta Core Tools Constants. 
    Use nicely with IntelliSense instead of remembering strings.
    """

    # Add information to long-term archival memory for later retrieval.  Use this tool to store facts, knowledge, or contex...
    ARCHIVAL_MEMORY_INSERT = "archival_memory_insert"

    # Search archival memory using semantic similarity to find relevant information.  This tool searches your long-term mem...
    ARCHIVAL_MEMORY_SEARCH = "archival_memory_search"

    # Search prior conversation history using hybrid search (text + semantic similarity).  Examples:         # Search all m...
    CONVERSATION_SEARCH = "conversation_search"

    # Append to the contents of core memory.
    CORE_MEMORY_APPEND = "core_memory_append"

    # Replace the contents of core memory. To delete memories, use an empty string for new_content.
    CORE_MEMORY_REPLACE = "core_memory_replace"

    # Fetch a webpage and convert it to markdown/text format using Exa API (if available) or trafilatura/readability.
    FETCH_WEBPAGE = "fetch_webpage"

    # This function is called when the agent is done rethinking the memory.
    FINISH_RETHINKING_MEMORY = "finish_rethinking_memory"

    # Searches file contents for pattern matches with surrounding context.  Results are paginated - shows 20 matches per ca...
    GREP_FILES = "grep_files"

    # Memory management tool with various sub-commands for memory block operations.  Examples:         # Replace text in a ...
    MEMORY = "memory"

    # Apply a simplified unified-diff style patch to one or more memory blocks.  Backwards compatible behavior: - If `patch...
    MEMORY_APPLY_PATCH = "memory_apply_patch"

    # Call the memory_finish_edits command when you are finished making edits (integrating all new information) into the me...
    MEMORY_FINISH_EDITS = "memory_finish_edits"

    # The memory_insert command allows you to insert text at a specific location in a memory block.  Examples:         # Up...
    MEMORY_INSERT = "memory_insert"

    # The memory_replace command allows you to replace a specific string in a memory block with a new string. This is used ...
    MEMORY_REPLACE = "memory_replace"

    # The memory_rethink command allows you to completely rewrite the contents of a memory block. Use this tool to make lar...
    MEMORY_RETHINK = "memory_rethink"

    # Open one or more files and load their contents into files section in core memory. Maximum of 5 files can be opened si...
    OPEN_FILES = "open_files"

    # Rewrite memory block for the main agent, new_memory should contain all current information from the block that is not...
    RETHINK_USER_MEMORY = "rethink_user_memory"

    # Run code in a sandbox. Supports Python, Javascript, Typescript, R, and Java.
    RUN_CODE = "run_code"

    # Run code with access to the tools of the agent. Only support python. You can directly invoke the tools of the agent i...
    RUN_CODE_WITH_TOOLS = "run_code_with_tools"

    # Look in long-term or earlier-conversation memory only when the user asks about something missing from the visible con...
    SEARCH_MEMORY = "search_memory"

    # Searches file contents using semantic meaning rather than exact matches.  Ideal for: - Finding conceptually related i...
    SEMANTIC_SEARCH_FILES = "semantic_search_files"

    # Sends a message to the human user.
    SEND_MESSAGE = "send_message"

    # Sends a message to a specific Letta agent within the same organization and waits for a response. The sender's identit...
    SEND_MESSAGE_TO_AGENT_AND_WAIT_FOR_REPLY = "send_message_to_agent_and_wait_for_reply"

    # Sends a message to a specific Letta agent within the same organization. The sender's identity is automatically includ...
    SEND_MESSAGE_TO_AGENT_ASYNC = "send_message_to_agent_async"

    # Sends a message to all agents within the same organization that match the specified tag criteria. Agents must possess...
    SEND_MESSAGE_TO_AGENTS_MATCHING_TAGS = "send_message_to_agents_matching_tags"

    # Persist dialogue that is about to fall out of the agent’s context window.
    STORE_MEMORIES = "store_memories"

    # Search the web using Exa's AI-powered search engine and retrieve relevant content.  Examples:     web_search("Tesla Q...
    WEB_SEARCH = "web_search"

