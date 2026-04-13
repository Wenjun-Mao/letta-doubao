"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  AgentDetails,
  ChatResult,
  OptionEntry,
  PlatformToolTestInvokeResult,
  PromptPersonaRevisionRecord,
  PersistentState,
  PlatformTool,
  attachTool,
  createAgent,
  fetchPromptPersonaRevisions,
  detachTool,
  fetchOptions,
  getAgentDetails,
  getPersistentState,
  getRawPrompt,
  listAgents,
  listTools,
  sendChat,
  testInvokeTool,
  updateAgentModel,
  updateCoreMemoryBlock,
  updateSystemPrompt,
} from "../../lib/api";

type AgentItem = {
  id: string;
  name: string;
  model: string;
  created_at: string;
  last_updated_at: string;
  last_interaction_at: string;
};

type ChatEntry = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timingMs: number | null;
};

type InspectorTab = "model" | "prompt" | "tools";
type PersistentTab = "summary" | "memory" | "history";
type EditorKind = "system" | "persona" | "human" | null;
type TimelineFilter = "all" | "assistant" | "tool" | "reasoning";

type DiffOp<T> = {
  type: "equal" | "insert" | "delete";
  value: T;
};

function toErrorMessage(exc: unknown): string {
  return exc instanceof Error ? exc.message : String(exc);
}

function extractAssistantReply(result: ChatResult): string {
  const reversed = [...(result.sequence || [])].reverse();
  const assistant = reversed.find((step) => step.type === "assistant" && step.content);
  return assistant?.content || "";
}

function shortId(value: string): string {
  if (value.length <= 28) {
    return value;
  }
  return `${value.slice(0, 14)}...${value.slice(-8)}`;
}

function formatTimestamp(value: string | undefined | null): string {
  if (!value) {
    return "N/A";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatLatency(valueMs: number | null): string {
  if (valueMs === null || !Number.isFinite(valueMs) || valueMs < 0) {
    return "";
  }
  if (valueMs < 1000) {
    return `${Math.round(valueMs)} ms`;
  }
  return `${(valueMs / 1000).toFixed(2)} s`;
}

function summarizeDescription(description: string, maxLength = 190): string {
  const normalized = (description || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "No description.";
  }
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength)}...`;
}

function parseToolExamples(description: string): { overview: string; examples: string[] } {
  const text = (description || "").replace(/\r\n/g, "\n").trim();
  if (!text) {
    return { overview: "No description.", examples: [] };
  }

  const marker = text.search(/examples?:/i);
  if (marker === -1) {
    return { overview: text, examples: [] };
  }

  const overview = text.slice(0, marker).trim() || "No overview provided.";
  const exampleBody = text.slice(marker).replace(/^examples?:\s*/i, "").trim();
  if (!exampleBody) {
    return { overview, examples: [] };
  }

  const segments = exampleBody
    .split(/\s+#\s+/)
    .map((segment) => segment.trim())
    .filter(Boolean);

  if (segments.length === 0) {
    return { overview, examples: [exampleBody] };
  }
  return { overview, examples: segments };
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function diffSequence<T>(source: T[], target: T[]): DiffOp<T>[] {
  const m = source.length;
  const n = target.length;
  const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));

  for (let i = 1; i <= m; i += 1) {
    for (let j = 1; j <= n; j += 1) {
      if (source[i - 1] === target[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  const ops: DiffOp<T>[] = [];
  let i = m;
  let j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && source[i - 1] === target[j - 1]) {
      ops.push({ type: "equal", value: source[i - 1] });
      i -= 1;
      j -= 1;
      continue;
    }

    if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.push({ type: "insert", value: target[j - 1] });
      j -= 1;
      continue;
    }

    ops.push({ type: "delete", value: source[i - 1] });
    i -= 1;
  }

  return ops.reverse();
}

function renderInlineDiff(oldLine: string, newLine: string): { oldHtml: string; newHtml: string } {
  const ops = diffSequence([...oldLine], [...newLine]);
  let oldHtml = "";
  let newHtml = "";

  for (const op of ops) {
    const escaped = escapeHtml(op.value);
    if (op.type === "equal") {
      oldHtml += escaped;
      newHtml += escaped;
      continue;
    }
    if (op.type === "delete") {
      oldHtml += `<span class=\"diff-removed\">${escaped}</span>`;
      continue;
    }
    newHtml += `<span class=\"diff-added\">${escaped}</span>`;
  }

  return { oldHtml, newHtml };
}

function highlightDiff(oldText: string, newText: string): string {
  const oldValue = oldText || "";
  const newValue = newText || "";
  if (oldValue === newValue) {
    return `<div class=\"diff-line\">${escapeHtml(newValue)}</div>`;
  }

  const lineOps = diffSequence(oldValue.split("\n"), newValue.split("\n"));
  const chunks: string[] = [];

  for (let idx = 0; idx < lineOps.length; idx += 1) {
    const current = lineOps[idx];
    if (current.type === "equal") {
      chunks.push(`<div class=\"diff-line\">${escapeHtml(current.value)}</div>`);
      continue;
    }

    const next = lineOps[idx + 1];
    if (current.type === "delete" && next && next.type === "insert") {
      const inline = renderInlineDiff(current.value, next.value);
      chunks.push(`<div class=\"diff-line diff-line-removed\"><span class=\"diff-marker\">[-]</span>${inline.oldHtml || " "}</div>`);
      chunks.push(`<div class=\"diff-line diff-line-added\"><span class=\"diff-marker\">[+]</span>${inline.newHtml || " "}</div>`);
      idx += 1;
      continue;
    }

    if (current.type === "insert" && next && next.type === "delete") {
      const inline = renderInlineDiff(next.value, current.value);
      chunks.push(`<div class=\"diff-line diff-line-removed\"><span class=\"diff-marker\">[-]</span>${inline.oldHtml || " "}</div>`);
      chunks.push(`<div class=\"diff-line diff-line-added\"><span class=\"diff-marker\">[+]</span>${inline.newHtml || " "}</div>`);
      idx += 1;
      continue;
    }

    if (current.type === "delete") {
      chunks.push(`<div class=\"diff-line diff-line-removed\"><span class=\"diff-marker\">[-]</span><span class=\"diff-removed\">${escapeHtml(current.value)}</span></div>`);
      continue;
    }

    chunks.push(`<div class=\"diff-line diff-line-added\"><span class=\"diff-marker\">[+]</span><span class=\"diff-added\">${escapeHtml(current.value)}</span></div>`);
  }

  return chunks.join("");
}

function stepTone(stepType: string): string {
  const normalized = String(stepType || "").toLowerCase();
  if (normalized.includes("assistant")) {
    return "timeline-step assistant";
  }
  if (normalized.includes("tool_call")) {
    return "timeline-step tool-call";
  }
  if (normalized.includes("tool_return")) {
    return "timeline-step tool-return";
  }
  if (normalized.includes("reasoning")) {
    return "timeline-step reasoning";
  }
  return "timeline-step";
}

function stepMatchesFilter(stepType: string, filter: TimelineFilter): boolean {
  if (filter === "all") {
    return true;
  }

  const normalized = String(stepType || "").toLowerCase();
  if (filter === "assistant") {
    return normalized.includes("assistant");
  }
  if (filter === "tool") {
    return normalized.includes("tool_call") || normalized.includes("tool_return");
  }
  if (filter === "reasoning") {
    return normalized.includes("reasoning");
  }
  return true;
}

export default function AgentStudioPage() {
  const chatScrollRef = useRef<HTMLDivElement | null>(null);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editorBusy, setEditorBusy] = useState(false);
  const [modelBusy, setModelBusy] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [toolProbeBusy, setToolProbeBusy] = useState(false);
  const [rawPromptLoading, setRawPromptLoading] = useState(false);
  const [revisionLoading, setRevisionLoading] = useState(false);
  const [toolBusyId, setToolBusyId] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const [models, setModels] = useState<OptionEntry[]>([]);
  const [embeddings, setEmbeddings] = useState<OptionEntry[]>([]);
  const [prompts, setPrompts] = useState<OptionEntry[]>([]);

  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("model");
  const [persistentTab, setPersistentTab] = useState<PersistentTab>("summary");
  const [timelineFilter, setTimelineFilter] = useState<TimelineFilter>("all");
  const [persistentLimit, setPersistentLimit] = useState(120);

  const [createName, setCreateName] = useState("ade-agent");
  const [createModel, setCreateModel] = useState("");
  const [createPromptKey, setCreatePromptKey] = useState("custom_v2");
  const [createEmbedding, setCreateEmbedding] = useState("");
  const [modelEditValue, setModelEditValue] = useState("");

  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatEntry[]>([]);

  const [agentDetails, setAgentDetails] = useState<AgentDetails | null>(null);
  const [persistentState, setPersistentState] = useState<PersistentState | null>(null);
  const [lastResult, setLastResult] = useState<ChatResult | null>(null);
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null);

  const [showRawPrompt, setShowRawPrompt] = useState(false);
  const [rawPromptMessages, setRawPromptMessages] = useState<Array<{ role: string; content: string }>>([]);

  const [toolSearch, setToolSearch] = useState("");
  const [toolCatalog, setToolCatalog] = useState<PlatformTool[]>([]);
  const [toolDetailTool, setToolDetailTool] = useState<PlatformTool | null>(null);
  const [toolProbeInput, setToolProbeInput] = useState("请根据当前问题决定是否需要调用工具，再回答结果。");
  const [toolProbeExpected, setToolProbeExpected] = useState("");
  const [toolProbeResult, setToolProbeResult] = useState<PlatformToolTestInvokeResult | null>(null);
  const [revisionHistory, setRevisionHistory] = useState<PromptPersonaRevisionRecord[]>([]);

  const [editorKind, setEditorKind] = useState<EditorKind>(null);
  const [editorValue, setEditorValue] = useState("");

  const historyCount = Number(persistentState?.conversation_history?.total_persisted || 0);
  const memoryBlocks = persistentState?.memory_blocks || [];
  const toolsFromPersistent = persistentState?.tools || [];
  const humanBefore = String(lastResult?.memory_diff?.old?.human || "");
  const humanAfter = String(lastResult?.memory_diff?.new?.human || "");

  const selectedAgentName = useMemo(() => {
    const found = agents.find((item) => item.id === selectedAgentId);
    return found ? found.name : "";
  }, [agents, selectedAgentId]);

  const selectedAgentInfo = useMemo(() => {
    return agents.find((item) => item.id === selectedAgentId) || null;
  }, [agents, selectedAgentId]);

  const attachedToolIds = useMemo(() => {
    const ids = new Set<string>();
    for (const tool of toolsFromPersistent) {
      if (tool.id) {
        ids.add(tool.id);
      }
    }
    return ids;
  }, [toolsFromPersistent]);

  const displayToolCatalog = useMemo(() => {
    const normalized = toolCatalog.map((tool) => ({
      ...tool,
      attached_to_agent: tool.attached_to_agent ?? attachedToolIds.has(tool.id),
    }));

    normalized.sort((left, right) => {
      const leftAttached = Boolean(left.attached_to_agent);
      const rightAttached = Boolean(right.attached_to_agent);
      if (leftAttached !== rightAttached) {
        return leftAttached ? -1 : 1;
      }

      const byName = String(left.name || "").localeCompare(String(right.name || ""), undefined, {
        sensitivity: "base",
      });
      if (byName !== 0) {
        return byName;
      }

      return String(left.id || "").localeCompare(String(right.id || ""));
    });

    return normalized;
  }, [attachedToolIds, toolCatalog]);

  const filteredTimelineSteps = useMemo(() => {
    const sequence = lastResult?.sequence || [];
    return sequence.filter((step) => stepMatchesFilter(step.type, timelineFilter));
  }, [lastResult?.sequence, timelineFilter]);

  const openEditor = (kind: Exclude<EditorKind, null>, value: string) => {
    setEditorKind(kind);
    setEditorValue(value);
    setStatus("");
    setError("");
  };

  const closeEditor = () => {
    setEditorKind(null);
    setEditorValue("");
  };

  const hydrateChatFromPersistent = (payload: PersistentState) => {
    const items = payload.conversation_history?.items || [];
    const hydrated: ChatEntry[] = [];
    for (const item of items) {
      const messageType = String(item.message_type || "").toLowerCase();
      const content = String(item.content || "").replace(/\r\n/g, "\n").trim();
      if (!content) {
        continue;
      }
      if (messageType === "user_message") {
        hydrated.push({
          id: `${item.id}-u`,
          role: "user",
          content,
          timingMs: null,
        });
      }
      if (messageType === "assistant_message") {
        hydrated.push({
          id: `${item.id}-a`,
          role: "assistant",
          content,
          timingMs: null,
        });
      }
    }
    setChatHistory(hydrated);
  };

  const refreshAgentList = async () => {
    const payload = await listAgents(200, false);
    const mapped = payload.items.map((item) => ({
      id: item.id,
      name: item.name || item.id,
      model: item.model || "",
      created_at: item.created_at || "",
      last_updated_at: item.last_updated_at || "",
      last_interaction_at: item.last_interaction_at || "",
    }));
    setAgents(mapped);

    if (!selectedAgentId && mapped.length > 0) {
      setSelectedAgentId(mapped[0].id);
    }
  };

  const refreshToolCatalog = async (agentId: string, searchValue = toolSearch) => {
    if (!agentId) {
      setToolCatalog([]);
      return;
    }

    const payload = await listTools(searchValue, 300, agentId);
    setToolCatalog(payload.items || []);
  };

  const refreshRevisionHistory = async (agentId: string) => {
    if (!agentId) {
      setRevisionHistory([]);
      return;
    }

    setRevisionLoading(true);
    try {
      const payload = await fetchPromptPersonaRevisions(agentId, "", 120);
      setRevisionHistory(payload.items || []);
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setRevisionLoading(false);
    }
  };

  const refreshSelectedAgent = async (agentId: string, hydrateChat = false) => {
    if (!agentId) {
      return;
    }

    const [details, persistent] = await Promise.all([
      getAgentDetails(agentId),
      getPersistentState(agentId, persistentLimit),
    ]);

    setAgentDetails(details);
    setPersistentState(persistent);
    setModelEditValue(String(details.model || ""));
    if (hydrateChat) {
      hydrateChatFromPersistent(persistent);
    }

    if (inspectorTab === "tools") {
      await refreshToolCatalog(agentId);
    }
  };

  const loadRawPrompt = async () => {
    if (!selectedAgentId) {
      return;
    }
    setRawPromptLoading(true);
    try {
      const payload = await getRawPrompt(selectedAgentId);
      setRawPromptMessages(Array.isArray(payload.messages) ? payload.messages : []);
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setRawPromptLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const [optionsPayload, agentsPayload] = await Promise.all([fetchOptions(), listAgents(200, false)]);
        if (cancelled) {
          return;
        }

        setModels(optionsPayload.models || []);
        setEmbeddings(optionsPayload.embeddings || []);
        setPrompts(optionsPayload.prompts || []);
        setCreateModel(optionsPayload.defaults?.model || optionsPayload.models?.[0]?.key || "");
        setCreatePromptKey(optionsPayload.defaults?.prompt_key || "custom_v2");
        setCreateEmbedding(optionsPayload.defaults?.embedding || "");

        const mapped = agentsPayload.items.map((item) => ({
          id: item.id,
          name: item.name || item.id,
          model: item.model || "",
          created_at: item.created_at || "",
          last_updated_at: item.last_updated_at || "",
          last_interaction_at: item.last_interaction_at || "",
        }));
        setAgents(mapped);
        if (mapped.length > 0) {
          setSelectedAgentId(mapped[0].id);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(toErrorMessage(exc));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedAgentId) {
      return;
    }
    let cancelled = false;
    const run = async () => {
      try {
        await refreshSelectedAgent(selectedAgentId, false);
        setRawPromptMessages([]);
      } catch (exc) {
        if (!cancelled) {
          setError(toErrorMessage(exc));
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [selectedAgentId]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    const focus = (params.get("focus") || "").trim().toLowerCase();
    if (focus === "prompt") {
      setInspectorTab("prompt");
    }
    if (focus === "tools") {
      setInspectorTab("tools");
    }
    if (focus === "model") {
      setInspectorTab("model");
    }
  }, []);

  useEffect(() => {
    if (!selectedAgentId) {
      return;
    }
    if (inspectorTab === "tools") {
      void refreshToolCatalog(selectedAgentId);
    }
    if (inspectorTab === "prompt") {
      void refreshRevisionHistory(selectedAgentId);
    }
  }, [inspectorTab, selectedAgentId]);

  useEffect(() => {
    const node = chatScrollRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [chatHistory]);

  useEffect(() => {
    if (!toolDetailTool) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setToolDetailTool(null);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [toolDetailTool]);

  const onCreateAgent = async () => {
    if (!createModel.trim()) {
      setError("Please select a model before creating an agent.");
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      const created = await createAgent({
        name: createName.trim() || "ade-agent",
        model: createModel,
        prompt_key: createPromptKey,
        embedding: createEmbedding.trim() || null,
      });

      await refreshAgentList();
      setSelectedAgentId(created.id);
      setChatHistory([]);
      setLastResult(null);
      setRawPromptMessages([]);
      setStatus(`Created agent ${created.name} (${created.id})`);
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onSendMessage = async () => {
    if (!selectedAgentId) {
      setError("Select an agent first.");
      return;
    }
    const text = chatInput.trim();
    if (!text) {
      return;
    }

    setChatBusy(true);
    setError("");
    setStatus("");
    const startedAt = performance.now();
    setChatHistory((prev) => [
      ...prev,
      {
        id: `${Date.now()}-user`,
        role: "user",
        content: text,
        timingMs: null,
      },
    ]);
    setChatInput("");

    try {
      const result = await sendChat(selectedAgentId, text);
      const assistant = extractAssistantReply(result);
      const elapsedMs = Math.max(0, performance.now() - startedAt);

      setChatHistory((prev) => [
        ...prev,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content: assistant || "(No assistant message returned)",
          timingMs: elapsedMs,
        },
      ]);
      setLastResult(result);
      setLastLatencyMs(elapsedMs);

      await refreshSelectedAgent(selectedAgentId, false);
    } catch (exc) {
      const elapsedMs = Math.max(0, performance.now() - startedAt);
      setChatHistory((prev) => [
        ...prev,
        {
          id: `${Date.now()}-error`,
          role: "assistant",
          content: `Error: ${toErrorMessage(exc)}`,
          timingMs: elapsedMs,
        },
      ]);
      setError(toErrorMessage(exc));
    } finally {
      setChatBusy(false);
    }
  };

  const onPullExistingInfo = async () => {
    if (!selectedAgentId) {
      setError("Select an existing agent first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await refreshSelectedAgent(selectedAgentId, true);
      setStatus("Persistent conversation history hydrated into Studio chat.");
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onApplyModel = async () => {
    if (!selectedAgentId || !modelEditValue.trim()) {
      return;
    }
    setModelBusy(true);
    setError("");
    try {
      await updateAgentModel(selectedAgentId, modelEditValue.trim());
      await refreshSelectedAgent(selectedAgentId, false);
      await refreshAgentList();
      setStatus("Agent model updated.");
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setModelBusy(false);
    }
  };

  const onSaveEditor = async () => {
    if (!selectedAgentId || !editorKind) {
      return;
    }
    const value = editorValue.trim();
    if (!value) {
      setError("Editor value cannot be empty.");
      return;
    }

    setEditorBusy(true);
    setError("");
    try {
      if (editorKind === "system") {
        await updateSystemPrompt(selectedAgentId, value);
      }
      if (editorKind === "persona") {
        await updateCoreMemoryBlock(selectedAgentId, "persona", value);
      }
      if (editorKind === "human") {
        await updateCoreMemoryBlock(selectedAgentId, "human", value);
      }
      await refreshSelectedAgent(selectedAgentId, false);
      if (inspectorTab === "prompt") {
        await refreshRevisionHistory(selectedAgentId);
      }
      closeEditor();
      setStatus(`${editorKind} updated successfully.`);
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setEditorBusy(false);
    }
  };

  const onToggleTool = async (tool: PlatformTool) => {
    if (!selectedAgentId) {
      return;
    }
    setToolBusyId(tool.id);
    setError("");
    try {
      const isAttached = Boolean(tool.attached_to_agent ?? attachedToolIds.has(tool.id));
      if (isAttached) {
        await detachTool(selectedAgentId, tool.id);
        setStatus(`Detached tool ${tool.name}`);
      } else {
        await attachTool(selectedAgentId, tool.id);
        setStatus(`Attached tool ${tool.name}`);
      }
      await refreshToolCatalog(selectedAgentId);
      await refreshSelectedAgent(selectedAgentId, false);
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setToolBusyId("");
    }
  };

  const onToggleRawPrompt = async () => {
    const next = !showRawPrompt;
    setShowRawPrompt(next);
    if (next && rawPromptMessages.length === 0) {
      await loadRawPrompt();
    }
  };

  const onRunToolProbe = async () => {
    if (!selectedAgentId) {
      setError("Select an agent first.");
      return;
    }

    const input = toolProbeInput.trim();
    if (!input) {
      setError("Tool probe input cannot be empty.");
      return;
    }

    setToolProbeBusy(true);
    setError("");
    setStatus("");

    try {
      const payload = await testInvokeTool({
        agent_id: selectedAgentId,
        input,
        expected_tool_name: toolProbeExpected.trim() || undefined,
      });
      setToolProbeResult(payload);
      setLastResult(payload.result || null);
      setStatus(`Tool probe completed: ${payload.tool_call_count} tool call(s), ${payload.tool_return_count} return(s).`);
      await refreshSelectedAgent(selectedAgentId, false);
      if (inspectorTab === "prompt") {
        await refreshRevisionHistory(selectedAgentId);
      }
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setToolProbeBusy(false);
    }
  };

  const onRefreshPersistent = async () => {
    if (!selectedAgentId) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await refreshSelectedAgent(selectedAgentId, false);
      setStatus("Agent persistent state refreshed.");
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const personaValue = memoryBlocks.find((block) => block.label === "persona")?.value || "";
  const humanValue = memoryBlocks.find((block) => block.label === "human")?.value || "";

  return (
    <section className="studio-root">
      <div className="kicker">Merged Workspace</div>
      <h1 className="section-title">Agent Studio</h1>

      <div className="studio-layout">
        <aside className="card studio-panel">
          <h3>Inspector</h3>

          <div className="form-grid">
            <label className="field">
              <span>New agent name</span>
              <input className="input" value={createName} onChange={(e) => setCreateName(e.target.value)} />
            </label>
            <label className="field">
              <span>Model</span>
              <select className="input" value={createModel} onChange={(e) => setCreateModel(e.target.value)}>
                <option value="">Select model</option>
                {models.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Prompt</span>
              <select className="input" value={createPromptKey} onChange={(e) => setCreatePromptKey(e.target.value)}>
                {prompts.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Embedding</span>
              <select className="input" value={createEmbedding} onChange={(e) => setCreateEmbedding(e.target.value)}>
                <option value="">Use server default</option>
                {embeddings.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="button" onClick={onCreateAgent} disabled={busy || loading}>
              {busy ? "Creating..." : "Create Agent"}
            </button>
            <button className="button muted" onClick={() => void refreshAgentList()} disabled={busy || loading}>
              Refresh Agents
            </button>
          </div>

          <hr className="studio-divider" />

          <label className="field">
            <span>Existing agents</span>
            <select className="input" value={selectedAgentId} onChange={(e) => setSelectedAgentId(e.target.value)}>
              <option value="">Select agent</option>
              {agents.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.model})
                </option>
              ))}
            </select>
          </label>

          {selectedAgentInfo ? (
            <div className="code" style={{ marginTop: 8 }}>
              ID: {shortId(selectedAgentInfo.id)}
              {"\n"}
              Created: {formatTimestamp(selectedAgentInfo.created_at)}
              {"\n"}
              Last interaction: {formatTimestamp(selectedAgentInfo.last_interaction_at || selectedAgentInfo.last_updated_at)}
            </div>
          ) : null}

          <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="button muted" onClick={() => void onPullExistingInfo()} disabled={!selectedAgentId || busy}>
              Pull Existing Info
            </button>
            <button className="button muted" onClick={() => void onRefreshPersistent()} disabled={!selectedAgentId || busy}>
              Refresh Selected
            </button>
          </div>

          <p className="muted" style={{ marginTop: 10 }}>
            Active: {selectedAgentName || "none"}
          </p>
          <p className="muted">Conversation rows: {historyCount}</p>

          {agentDetails ? (
            <>
              <div className="studio-tabs">
                <button className={inspectorTab === "model" ? "tab-active" : "tab-item"} onClick={() => setInspectorTab("model")}>
                  Model
                </button>
                <button className={inspectorTab === "prompt" ? "tab-active" : "tab-item"} onClick={() => setInspectorTab("prompt")}>
                  Prompt
                </button>
                <button className={inspectorTab === "tools" ? "tab-active" : "tab-item"} onClick={() => setInspectorTab("tools")}>
                  Tools
                </button>
              </div>

              {inspectorTab === "model" ? (
                <div className="studio-stack">
                  <div className="field">
                    <span>Agent model override</span>
                    <select className="input" value={modelEditValue} onChange={(e) => setModelEditValue(e.target.value)}>
                      <option value="">Select model</option>
                      {models.map((item) => (
                        <option key={item.key} value={item.key}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                    <button className="button" onClick={() => void onApplyModel()} disabled={modelBusy || !selectedAgentId || !modelEditValue}>
                      {modelBusy ? "Applying..." : "Apply Model"}
                    </button>
                  </div>
                  <div className="code">
                    Type: {agentDetails.agent_type || "unknown"}
                    {"\n"}
                    Context window: {agentDetails.context_window_limit ?? "N/A"}
                    {"\n"}
                    Last interaction: {formatTimestamp(agentDetails.last_interaction_at || agentDetails.last_updated_at)}
                  </div>
                  {agentDetails.llm_config ? (
                    <div className="code">{JSON.stringify(agentDetails.llm_config, null, 2)}</div>
                  ) : null}
                </div>
              ) : null}

              {inspectorTab === "prompt" ? (
                <div className="studio-stack">
                  <div className="toolbar prompt-action-row">
                    <button className="prompt-action-button" onClick={() => openEditor("system", agentDetails.system || "")}>Edit System Prompt</button>
                    <button className="prompt-action-button" onClick={() => openEditor("persona", personaValue)}>Edit Persona</button>
                    <button className="prompt-action-button" onClick={() => openEditor("human", humanValue)}>Edit Human</button>
                    <button
                      className="prompt-action-button"
                      onClick={() => void refreshRevisionHistory(selectedAgentId)}
                      disabled={!selectedAgentId || revisionLoading}
                    >
                      {revisionLoading ? "Refreshing..." : "Refresh Timeline"}
                    </button>
                  </div>
                  <div className="code">{agentDetails.system || "No system prompt."}</div>

                  <div className="card" style={{ padding: 10 }}>
                    <div className="toolbar" style={{ justifyContent: "space-between" }}>
                      <strong>Revision Timeline</strong>
                      <span className="muted">{revisionHistory.length} record(s)</span>
                    </div>
                    {revisionHistory.length === 0 ? (
                      <p className="muted" style={{ marginTop: 8 }}>
                        No prompt/persona revisions recorded yet for this agent.
                      </p>
                    ) : (
                      <div className="studio-stack" style={{ marginTop: 8, maxHeight: 320, overflowY: "auto" }}>
                        {revisionHistory.map((record) => (
                          <div className="card revision-item" style={{ padding: 10 }} key={record.revision_id}>
                            <div className="toolbar" style={{ justifyContent: "space-between" }}>
                              <strong>{record.field}</strong>
                              <span className="muted">{formatTimestamp(record.recorded_at)}</span>
                            </div>
                            <p className="muted" style={{ marginTop: 6 }}>
                              source: {record.source} | delta: {record.delta_length >= 0 ? `+${record.delta_length}` : record.delta_length}
                            </p>
                            <details style={{ marginTop: 8 }}>
                              <summary>View before/after preview</summary>
                              <div className="code" style={{ marginTop: 8 }}>
                                [before]
                                {"\n"}
                                {record.before_preview || "(empty)"}
                                {"\n\n"}
                                [after]
                                {"\n"}
                                {record.after_preview || "(empty)"}
                              </div>
                            </details>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : null}

              {inspectorTab === "tools" ? (
                <div className="studio-stack">
                  <div className="toolbar">
                    <input
                      className="input"
                      value={toolSearch}
                      placeholder="Search tools"
                      onChange={(e) => setToolSearch(e.target.value)}
                    />
                    <button className="button muted" onClick={() => void refreshToolCatalog(selectedAgentId)} disabled={!selectedAgentId}>
                      Refresh
                    </button>
                  </div>
                  {displayToolCatalog.length === 0 ? (
                    <p className="muted">No tools found.</p>
                  ) : (
                    <div className="studio-stack">
                      {displayToolCatalog.map((tool) => {
                        const isAttached = Boolean(tool.attached_to_agent);
                        const preview = summarizeDescription(tool.description || "");
                        return (
                          <div key={tool.id} className="card tool-card" style={{ padding: 10 }}>
                            <div className="tool-card-header">
                              <strong className="tool-card-name">{tool.name}</strong>
                              <button
                                className={`button tool-action-button ${isAttached ? "danger" : "success"}`}
                                onClick={() => void onToggleTool(tool)}
                                disabled={toolBusyId === tool.id || !selectedAgentId}
                              >
                                {toolBusyId === tool.id
                                  ? "Working..."
                                  : isAttached
                                    ? "Detach"
                                    : "Attach"}
                              </button>
                            </div>
                            <div className="toolbar tool-card-actions">
                              <button
                                className="button muted tool-detail-button"
                                title="View full details"
                                onClick={() => setToolDetailTool(tool)}
                              >
                                View details
                              </button>
                            </div>
                            <p className="muted tool-card-description" style={{ marginTop: 8 }}>{preview}</p>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div className="card" style={{ padding: 10 }}>
                    <h4 style={{ margin: 0 }}>Tool Probe (Phase-2)</h4>
                    <p className="muted" style={{ marginTop: 8 }}>
                      Sends a runtime message and reports detected tool calls/returns.
                    </p>
                    <label className="field" style={{ marginTop: 8 }}>
                      <span>Probe input</span>
                      <textarea
                        className="input"
                        style={{ minHeight: 84, resize: "vertical" }}
                        value={toolProbeInput}
                        onChange={(e) => setToolProbeInput(e.target.value)}
                      />
                    </label>
                    <label className="field" style={{ marginTop: 8 }}>
                      <span>Expected tool name (optional)</span>
                      <input
                        className="input"
                        value={toolProbeExpected}
                        onChange={(e) => setToolProbeExpected(e.target.value)}
                        placeholder="e.g. search_documents"
                      />
                    </label>
                    <div className="toolbar" style={{ marginTop: 8 }}>
                      <button
                        className="button"
                        onClick={() => void onRunToolProbe()}
                        disabled={!selectedAgentId || toolProbeBusy}
                      >
                        {toolProbeBusy ? "Running..." : "Run Tool Probe"}
                      </button>
                    </div>
                    {toolProbeResult ? (
                      <div className="code" style={{ marginTop: 8 }}>
                        tool_call_count: {toolProbeResult.tool_call_count}
                        {"\n"}
                        tool_return_count: {toolProbeResult.tool_return_count}
                        {"\n"}
                        expected_tool_name: {toolProbeResult.expected_tool_name || "(none)"}
                        {"\n"}
                        expected_tool_matched: {String(toolProbeResult.expected_tool_matched)}
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </>
          ) : null}
        </aside>

        <main className="card studio-panel">
          <h3>Chat</h3>
          <div className="chat-scroll" ref={chatScrollRef}>
            {chatHistory.length === 0 ? (
              <p className="muted">Send a message or use Pull Existing Info to hydrate history.</p>
            ) : (
              chatHistory.map((entry) => (
                <div key={entry.id} className={`chat-row ${entry.role === "user" ? "user" : "assistant"}`}>
                  <div className="chat-bubble">
                    <div className="chat-meta">
                      <span>{entry.role === "user" ? "You" : "Assistant"}</span>
                      {entry.role === "assistant" && entry.timingMs !== null ? (
                        <span>{formatLatency(entry.timingMs)}</span>
                      ) : null}
                    </div>
                    <div className="chat-content">{entry.content}</div>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="toolbar" style={{ marginTop: 12 }}>
            <textarea
              className="input"
              style={{ minHeight: 82, resize: "vertical", flex: 1 }}
              placeholder="Type a message (Enter to send)"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void onSendMessage();
                }
              }}
            />
            <button className="button" onClick={() => void onSendMessage()} disabled={chatBusy || !selectedAgentId}>
              {chatBusy ? "Sending..." : "Send"}
            </button>
          </div>
        </main>

        <aside className="card studio-panel">
          <h3>Execution Trace</h3>
          {lastLatencyMs !== null ? <p className="muted">Last response latency: {formatLatency(lastLatencyMs)}</p> : null}
          <div className="toolbar" style={{ marginTop: 8 }}>
            <button
              className={timelineFilter === "all" ? "button" : "button muted"}
              onClick={() => setTimelineFilter("all")}
            >
              All
            </button>
            <button
              className={timelineFilter === "assistant" ? "button" : "button muted"}
              onClick={() => setTimelineFilter("assistant")}
            >
              Assistant
            </button>
            <button
              className={timelineFilter === "tool" ? "button" : "button muted"}
              onClick={() => setTimelineFilter("tool")}
            >
              Tool
            </button>
            <button
              className={timelineFilter === "reasoning" ? "button" : "button muted"}
              onClick={() => setTimelineFilter("reasoning")}
            >
              Reasoning
            </button>
          </div>

          {filteredTimelineSteps.length ? (
            <div className="studio-stack" style={{ marginTop: 8 }}>
              {filteredTimelineSteps.map((step, index) => (
                <div className={stepTone(step.type)} key={`${step.type}-${index}`}>
                  <div className="timeline-type">{step.type}</div>
                  {step.name ? <div className="timeline-name">{step.name}</div> : null}
                  {step.content ? <div className="timeline-content">{step.content}</div> : null}
                  {step.arguments || step.tool_arguments ? (
                    <pre className="code">{String(step.arguments || step.tool_arguments || "")}</pre>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No runtime steps yet.</p>
          )}

          {lastResult ? (
            <div className="studio-stack" style={{ marginTop: 10 }}>
              <h4 style={{ margin: 0 }}>Human Memory Diff</h4>
              <div className="code memory-diff" dangerouslySetInnerHTML={{ __html: highlightDiff(humanBefore, humanAfter) }} />
            </div>
          ) : null}

          <hr className="studio-divider" />

          <div className="toolbar" style={{ justifyContent: "space-between" }}>
            <h4 style={{ margin: 0 }}>Raw Prompt Context</h4>
            <button className="button muted" onClick={() => void onToggleRawPrompt()}>
              {showRawPrompt ? "Hide" : "Show"}
            </button>
          </div>
          {showRawPrompt ? (
            rawPromptLoading ? (
              <p className="muted">Loading raw prompt...</p>
            ) : (
              <div className="studio-stack">
                {rawPromptMessages.length === 0 ? (
                  <p className="muted">No prompt payload loaded.</p>
                ) : (
                  rawPromptMessages.map((message, idx) => (
                    <div className="code" key={`${message.role}-${idx}`}>
                      [{message.role}]
                      {"\n"}
                      {message.content}
                    </div>
                  ))
                )}
              </div>
            )
          ) : null}

          <hr className="studio-divider" />

          <div className="toolbar" style={{ justifyContent: "space-between" }}>
            <h4 style={{ margin: 0 }}>Persistent State</h4>
            <button className="button muted" onClick={() => void onRefreshPersistent()} disabled={!selectedAgentId || busy}>
              Refresh
            </button>
          </div>
          <div className="toolbar" style={{ marginTop: 8 }}>
            <label className="field" style={{ width: 150 }}>
              <span>History limit</span>
              <input
                className="input"
                type="number"
                min={10}
                max={500}
                value={persistentLimit}
                onChange={(e) => setPersistentLimit(Math.max(10, Math.min(500, Number(e.target.value) || 120)))}
              />
            </label>
          </div>

          <div className="studio-tabs" style={{ marginTop: 10 }}>
            <button className={persistentTab === "summary" ? "tab-active" : "tab-item"} onClick={() => setPersistentTab("summary")}>
              Summary
            </button>
            <button className={persistentTab === "memory" ? "tab-active" : "tab-item"} onClick={() => setPersistentTab("memory")}>
              Memory
            </button>
            <button className={persistentTab === "history" ? "tab-active" : "tab-item"} onClick={() => setPersistentTab("history")}>
              History
            </button>
          </div>

          {persistentTab === "summary" && persistentState ? (
            <div className="code" style={{ marginTop: 8 }}>
              Agent: {persistentState.agent?.id || "N/A"}
              {"\n"}
              Name: {persistentState.agent?.name || "N/A"}
              {"\n"}
              Model: {persistentState.agent?.model || "N/A"}
              {"\n"}
              History rows: {persistentState.conversation_history?.displayed || 0} / {persistentState.conversation_history?.total_persisted || 0}
              {"\n"}
              Counts by type:
              {"\n"}
              {JSON.stringify(persistentState.conversation_history?.counts_by_type || {}, null, 2)}
            </div>
          ) : null}

          {persistentTab === "memory" ? (
            <div className="studio-stack" style={{ marginTop: 8 }}>
              {memoryBlocks.map((block) => (
                <div key={block.label} className="card" style={{ padding: 10 }}>
                  <div className="toolbar" style={{ justifyContent: "space-between" }}>
                    <strong>{block.label}</strong>
                    {block.label === "persona" ? (
                      <button className="button muted" onClick={() => openEditor("persona", block.value)}>Edit</button>
                    ) : null}
                    {block.label === "human" ? (
                      <button className="button muted" onClick={() => openEditor("human", block.value)}>Edit</button>
                    ) : null}
                  </div>
                  {block.description ? <p className="muted" style={{ marginTop: 8 }}>{block.description}</p> : null}
                  <div className="code" style={{ marginTop: 8 }}>{block.value}</div>
                </div>
              ))}
            </div>
          ) : null}

          {persistentTab === "history" && persistentState ? (
            <div className="studio-stack" style={{ marginTop: 8, maxHeight: 500, overflowY: "auto" }}>
              {(persistentState.conversation_history?.items || []).map((item) => (
                <div className="card" style={{ padding: 10 }} key={`${item.id}-${item.created_at}`}>
                  <div className="toolbar" style={{ justifyContent: "space-between" }}>
                    <strong>{item.message_type}</strong>
                    <span className="muted">{formatTimestamp(item.created_at)}</span>
                  </div>
                  <div className="code" style={{ marginTop: 8 }}>{item.content}</div>
                </div>
              ))}
            </div>
          ) : null}
        </aside>
      </div>

      {editorKind ? (
        <div className="editor-overlay">
          <div className="editor-card">
            <h3 style={{ marginTop: 0 }}>Edit {editorKind}</h3>
            <textarea
              className="input"
              style={{ minHeight: 260, resize: "vertical" }}
              value={editorValue}
              onChange={(e) => setEditorValue(e.target.value)}
            />
            <div className="toolbar" style={{ marginTop: 10, justifyContent: "flex-end" }}>
              <button className="button muted" onClick={closeEditor} disabled={editorBusy}>
                Cancel
              </button>
              <button className="button" onClick={() => void onSaveEditor()} disabled={editorBusy}>
                {editorBusy ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {toolDetailTool ? (
        <div
          className="editor-overlay"
          onClick={() => setToolDetailTool(null)}
          role="dialog"
          aria-modal="true"
          aria-label={`Tool details: ${toolDetailTool.name}`}
        >
          <div className="editor-card tool-detail-card" onClick={(event) => event.stopPropagation()}>
            <div className="tool-detail-header">
              <div>
                <h3 style={{ margin: 0 }}>{toolDetailTool.name}</h3>
                <div className="tool-detail-meta">
                  <span className="tool-detail-badge">{toolDetailTool.attached_to_agent ? "Attached" : "Not Attached"}</span>
                  <span className="tool-detail-badge">Type: {toolDetailTool.tool_type || "unknown"}</span>
                  <span className="tool-detail-badge">Source: {toolDetailTool.source_type || "unknown"}</span>
                </div>
              </div>
              <button className="button muted" onClick={() => setToolDetailTool(null)}>
                Close (Esc)
              </button>
            </div>

            {(() => {
              const parsed = parseToolExamples(toolDetailTool.description || "");
              return (
                <>
                  <p className="tool-detail-overview">{parsed.overview}</p>
                  {parsed.examples.length > 0 ? (
                    <>
                      <div className="tool-detail-section-title">Examples</div>
                      {parsed.examples.map((example, idx) => (
                        <pre className="code tool-detail-code" key={`${toolDetailTool.id}-example-${idx}`}>
                          {example}
                        </pre>
                      ))}
                    </>
                  ) : (
                    <>
                      <div className="tool-detail-section-title">Full Description</div>
                      <pre className="code tool-detail-code">{toolDetailTool.description || "No description."}</pre>
                    </>
                  )}
                </>
              );
            })()}
          </div>
        </div>
      ) : null}

      {status ? (
        <div className="card" style={{ marginTop: 12, borderColor: "#bbf7d0" }}>
          <h3>Status</h3>
          <p className="muted">{status}</p>
        </div>
      ) : null}

      {error ? (
        <div className="card" style={{ marginTop: 12, borderColor: "#fecaca" }}>
          <h3>Error</h3>
          <p className="muted">{error}</p>
        </div>
      ) : null}
    </section>
  );
}
