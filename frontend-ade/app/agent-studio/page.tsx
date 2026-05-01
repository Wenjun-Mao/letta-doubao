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
  archiveAgent,
  createAgent,
  fetchPromptPersonaRevisions,
  detachTool,
  fetchOptions,
  getAgentDetails,
  getPersistentState,
  getRawPrompt,
  listAgents,
  listTools,
  purgeAgent,
  restoreAgent,
  sendChat,
  testInvokeTool,
  updateAgentModel,
  updateCoreMemoryBlock,
  updateSystemPrompt,
} from "../../lib/api";
import { useI18n } from "../../lib/i18n";

type AgentItem = {
  id: string;
  name: string;
  model: string;
  created_at: string;
  last_updated_at: string;
  last_interaction_at: string;
  archived: boolean;
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
const AGENT_CREATE_SCENARIO = "chat" as const;

type DiffOp<T> = {
  type: "equal" | "insert" | "delete";
  value: T;
};

const TOOL_PROBE_DEFAULT_EN = "Decide whether to call a tool for this request, then return a concise answer.";
const TOOL_PROBE_DEFAULT_ZH = "请根据当前问题决定是否需要调用工具，再回答结果。";
const AGENT_STUDIO_DEFAULT_TIMEOUT_SECONDS = "180";
const AGENT_STUDIO_DEFAULT_RETRY_COUNT = "0";

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

function formatTimestamp(value: string | undefined | null, locale: "en" | "zh" = "en"): string {
  if (!value) {
    return "N/A";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString(locale === "zh" ? "zh-CN" : "en-US", {
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

function summarizeDescription(description: string, fallbackText = "No description.", maxLength = 190): string {
  const normalized = (description || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return fallbackText;
  }
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength)}...`;
}

function parsePositiveFloat(value: string): number | null {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function parseRetryCount(value: string): number | null {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 5) {
    return null;
  }
  return parsed;
}

function parseOptionalTemperature(value: string): number | undefined | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  const parsed = Number.parseFloat(trimmed);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 2) {
    return null;
  }
  return parsed;
}

function parseOptionalTopP(value: string): number | undefined | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  const parsed = Number.parseFloat(trimmed);
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 1) {
    return null;
  }
  return parsed;
}

function parseToolExamples(
  description: string,
  fallbackNoDescription = "No description.",
  fallbackNoOverview = "No overview provided.",
): { overview: string; examples: string[] } {
  const text = (description || "").replace(/\r\n/g, "\n").trim();
  if (!text) {
    return { overview: fallbackNoDescription, examples: [] };
  }

  const marker = text.search(/examples?:/i);
  if (marker === -1) {
    return { overview: text, examples: [] };
  }

  const overview = text.slice(0, marker).trim() || fallbackNoOverview;
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
  const { locale } = useI18n();
  const t = (en: string, zh: string) => (locale === "zh" ? zh : en);
  const modelOptionLabel = (option: OptionEntry): string => {
    const rawKey = String(option.key || "").trim();
    const rawLabel = String(option.label || "").trim();
    const base = rawLabel && rawLabel !== rawKey ? `${rawLabel} (${rawKey})` : rawKey;
    if (option.available === false) {
      return `${base}${t(" [Unavailable]", " [不可用]")}`;
    }
    return base;
  };

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
  const [personas, setPersonas] = useState<OptionEntry[]>([]);

  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [includeArchivedAgents, setIncludeArchivedAgents] = useState(false);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("model");
  const [persistentTab, setPersistentTab] = useState<PersistentTab>("summary");
  const [timelineFilter, setTimelineFilter] = useState<TimelineFilter>("all");
  const [persistentLimit, setPersistentLimit] = useState(120);

  const [createName, setCreateName] = useState("ade-agent");
  const [createModel, setCreateModel] = useState("");
  const [createPromptKey, setCreatePromptKey] = useState("chat_v20260418");
  const [createPersonaKey, setCreatePersonaKey] = useState("chat_linxiaotang");
  const [createEmbedding, setCreateEmbedding] = useState("");
  const [createTemperature, setCreateTemperature] = useState("");
  const [createTopP, setCreateTopP] = useState("");
  const [modelEditValue, setModelEditValue] = useState("");

  const [chatInput, setChatInput] = useState("");
  const [runtimeTimeoutSeconds, setRuntimeTimeoutSeconds] = useState(AGENT_STUDIO_DEFAULT_TIMEOUT_SECONDS);
  const [runtimeRetryCount, setRuntimeRetryCount] = useState(AGENT_STUDIO_DEFAULT_RETRY_COUNT);
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
  const [toolProbeInput, setToolProbeInput] = useState(() => (locale === "zh" ? TOOL_PROBE_DEFAULT_ZH : TOOL_PROBE_DEFAULT_EN));
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
  const selectedAgentArchived = Boolean(selectedAgentInfo?.archived);

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

  const resetSelectedAgentState = () => {
    setAgentDetails(null);
    setPersistentState(null);
    setChatHistory([]);
    setLastResult(null);
    setLastLatencyMs(null);
    setRawPromptMessages([]);
    setToolCatalog([]);
    setToolProbeResult(null);
    setRevisionHistory([]);
    setModelEditValue("");
  };

  const refreshAgentList = async (includeArchived = includeArchivedAgents) => {
    const payload = await listAgents(200, false, includeArchived);
    const mapped = payload.items.map((item) => ({
      id: item.id,
      name: item.name || item.id,
      model: item.model || "",
      created_at: item.created_at || "",
      last_updated_at: item.last_updated_at || "",
      last_interaction_at: item.last_interaction_at || "",
      archived: Boolean(item.archived),
    }));
    setAgents(mapped);

    const hasSelected = mapped.some((item) => item.id === selectedAgentId);
    if (!selectedAgentId && mapped.length > 0) {
      setSelectedAgentId(mapped[0].id);
      return;
    }
    if (!hasSelected) {
      const nextAgentId = mapped[0]?.id || "";
      setSelectedAgentId(nextAgentId);
      if (!nextAgentId) {
        resetSelectedAgentState();
      }
    }
  };

  const refreshCreationOptions = async (forceRefresh = false) => {
    const optionsPayload = await fetchOptions(AGENT_CREATE_SCENARIO, forceRefresh ? { refresh: true } : undefined);

    const nextModels = optionsPayload.models || [];
    const nextEmbeddings = optionsPayload.embeddings || [];
    const nextPrompts = optionsPayload.prompts || [];
    const nextPersonas = optionsPayload.personas || [];

    setModels(nextModels);
    setEmbeddings(nextEmbeddings);
    setPrompts(nextPrompts);
    setPersonas(nextPersonas);

    setCreateModel((current) => (current && nextModels.some((item) => item.key === current) ? current : ""));
    setCreatePromptKey((current) => {
      if (current && nextPrompts.some((item) => item.key === current)) {
        return current;
      }
      return optionsPayload.defaults?.prompt_key || nextPrompts[0]?.key || "chat_v20260418";
    });
    setCreatePersonaKey((current) => {
      if (current && nextPersonas.some((item) => item.key === current)) {
        return current;
      }
      return optionsPayload.defaults?.persona_key || nextPersonas[0]?.key || "chat_linxiaotang";
    });
    setCreateEmbedding((current) => {
      if (current && nextEmbeddings.some((item) => item.key === current)) {
        return current;
      }
      return optionsPayload.defaults?.embedding || "";
    });
    setCreateTemperature((current) => current || String(optionsPayload.agent_studio?.temperature ?? ""));
    setCreateTopP((current) => current || String(optionsPayload.agent_studio?.top_p ?? ""));
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
        const [optionsPayload, agentsPayload] = await Promise.all([
          fetchOptions(AGENT_CREATE_SCENARIO),
          listAgents(200, false, false),
        ]);
        if (cancelled) {
          return;
        }

        setModels(optionsPayload.models || []);
        setEmbeddings(optionsPayload.embeddings || []);
        setPrompts(optionsPayload.prompts || []);
        setPersonas(optionsPayload.personas || []);

        const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
        const requestedPromptKey = (params?.get("promptKey") || "").trim();
        const requestedPersonaKey = (params?.get("personaKey") || "").trim();

        const promptKeys = (optionsPayload.prompts || []).map((item) => item.key);
        const personaKeys = (optionsPayload.personas || []).map((item) => item.key);

        const resolvedPromptKey =
          requestedPromptKey && promptKeys.includes(requestedPromptKey)
            ? requestedPromptKey
            : optionsPayload.defaults?.prompt_key || optionsPayload.prompts?.[0]?.key || "chat_v20260418";

        const resolvedPersonaKey =
          requestedPersonaKey && personaKeys.includes(requestedPersonaKey)
            ? requestedPersonaKey
            : optionsPayload.defaults?.persona_key || optionsPayload.personas?.[0]?.key || "chat_linxiaotang";

        setCreateModel("");
        setCreatePromptKey(resolvedPromptKey);
        setCreatePersonaKey(resolvedPersonaKey);
        setCreateEmbedding(optionsPayload.defaults?.embedding || "");

        const mapped = agentsPayload.items.map((item) => ({
          id: item.id,
          name: item.name || item.id,
          model: item.model || "",
          created_at: item.created_at || "",
          last_updated_at: item.last_updated_at || "",
          last_interaction_at: item.last_interaction_at || "",
          archived: Boolean(item.archived),
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
    const localizedDefaultProbeInput = locale === "zh" ? TOOL_PROBE_DEFAULT_ZH : TOOL_PROBE_DEFAULT_EN;
    setToolProbeInput((current) => {
      if (!current.trim() || current === TOOL_PROBE_DEFAULT_EN || current === TOOL_PROBE_DEFAULT_ZH) {
        return localizedDefaultProbeInput;
      }
      return current;
    });
  }, [locale]);

  useEffect(() => {
    void refreshAgentList(includeArchivedAgents);
  }, [includeArchivedAgents]);

  useEffect(() => {
    if (!selectedAgentId) {
      resetSelectedAgentState();
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
      setError(t("Please select a model before creating an agent.", "创建智能体前请先选择模型。"));
      return;
    }
    const parsedTemperature = parseOptionalTemperature(createTemperature);
    if (parsedTemperature === null) {
      setError(t("Temperature must be between 0 and 2.", "Temperature 必须在 0 到 2 之间。"));
      return;
    }
    const parsedTopP = parseOptionalTopP(createTopP);
    if (parsedTopP === null) {
      setError(t("Top P must be greater than 0 and at most 1.", "Top P 必须大于 0 且不超过 1。"));
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      const created = await createAgent({
        scenario: AGENT_CREATE_SCENARIO,
        name: createName.trim() || "ade-agent",
        model: createModel,
        prompt_key: createPromptKey,
        persona_key: createPersonaKey,
        embedding: createEmbedding.trim() || null,
        temperature: parsedTemperature,
        top_p: parsedTopP,
      });

      await refreshAgentList(includeArchivedAgents);
      setSelectedAgentId(created.id);
      setChatHistory([]);
      setLastResult(null);
      setRawPromptMessages([]);
      setStatus(t(`Created agent ${created.name} (${created.id})`, `已创建智能体 ${created.name} (${created.id})`));
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onReloadModels = async () => {
    setBusy(true);
    setError("");
    try {
      await refreshCreationOptions(true);
      setStatus(t("Model options reloaded from backend.", "模型选项已从后端重新加载。"));
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onArchiveAgent = async () => {
    if (!selectedAgentId || selectedAgentArchived) {
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      await archiveAgent(selectedAgentId);
      await refreshAgentList(includeArchivedAgents);
      setStatus(t("Agent archived. Use Restore to make it active again.", "智能体已归档。可使用 Restore 恢复为活跃状态。"));
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onRestoreAgent = async () => {
    if (!selectedAgentId || !selectedAgentArchived) {
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      await restoreAgent(selectedAgentId);
      await refreshAgentList(includeArchivedAgents);
      setStatus(t("Agent restored and active again.", "智能体已恢复并重新激活。"));
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onPurgeAgent = async () => {
    if (!selectedAgentId || !selectedAgentArchived) {
      return;
    }

    const confirmed = window.confirm(
      t(
        "This will permanently delete the archived agent and cannot be undone. Continue?",
        "这将永久删除已归档智能体且不可恢复。是否继续？",
      ),
    );
    if (!confirmed) {
      return;
    }

    const targetAgentId = selectedAgentId;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await purgeAgent(targetAgentId);
      setSelectedAgentId("");
      resetSelectedAgentState();
      await refreshAgentList(includeArchivedAgents);
      setStatus(t("Archived agent permanently deleted.", "已永久删除归档智能体。"));
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onSendMessage = async () => {
    if (!selectedAgentId) {
      setError(t("Select an agent first.", "请先选择智能体。"));
      return;
    }
    if (selectedAgentArchived) {
      setError(t("Archived agents cannot run chat. Restore first.", "归档智能体不可对话，请先恢复。"));
      return;
    }
    const text = chatInput.trim();
    if (!text) {
      return;
    }
    const parsedTimeoutSeconds = parsePositiveFloat(runtimeTimeoutSeconds);
    if (parsedTimeoutSeconds === null) {
      setError(t("Timeout must be a positive number.", "超时时间必须是正数。"));
      return;
    }
    const parsedRetryCount = parseRetryCount(runtimeRetryCount);
    if (parsedRetryCount === null) {
      setError(t("Retry count must be an integer between 0 and 5.", "重试次数必须是 0 到 5 之间的整数。"));
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
      const result = await sendChat(selectedAgentId, text, {
        timeout_seconds: parsedTimeoutSeconds,
        retry_count: parsedRetryCount,
      });
      const assistant = extractAssistantReply(result);
      const elapsedMs = Math.max(0, performance.now() - startedAt);

      setChatHistory((prev) => [
        ...prev,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content: assistant || t("(No assistant message returned)", "（未返回助手消息）"),
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
          content: t(`Error: ${toErrorMessage(exc)}`, `错误：${toErrorMessage(exc)}`),
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
      setError(t("Select an existing agent first.", "请先选择现有智能体。"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await refreshSelectedAgent(selectedAgentId, true);
      setStatus(t("Persistent conversation history hydrated into Studio chat.", "已将持久化对话历史载入工作台聊天区。"));
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
    if (selectedAgentArchived) {
      setError(t("Archived agents cannot be mutated. Restore first.", "归档智能体不可修改，请先恢复。"));
      return;
    }
    setModelBusy(true);
    setError("");
    try {
      await updateAgentModel(selectedAgentId, modelEditValue.trim());
      await refreshSelectedAgent(selectedAgentId, false);
      await refreshAgentList(includeArchivedAgents);
      setStatus(t("Agent model updated.", "智能体模型已更新。"));
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
    if (selectedAgentArchived) {
      setError(t("Archived agents cannot be mutated. Restore first.", "归档智能体不可修改，请先恢复。"));
      return;
    }
    const value = editorValue.trim();
    if (!value) {
      setError(t("Editor value cannot be empty.", "编辑内容不能为空。"));
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
      const editorLabel =
        editorKind === "system"
          ? t("system", "system")
          : editorKind === "persona"
            ? t("persona", "persona")
            : t("human", "human");
      setStatus(t(`${editorLabel} updated successfully.`, `${editorLabel} 已更新。`));
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
    if (selectedAgentArchived) {
      setError(t("Archived agents cannot change tools. Restore first.", "归档智能体不可变更工具，请先恢复。"));
      return;
    }
    setToolBusyId(tool.id);
    setError("");
    try {
      const isAttached = Boolean(tool.attached_to_agent ?? attachedToolIds.has(tool.id));
      if (isAttached) {
        await detachTool(selectedAgentId, tool.id);
        setStatus(t(`Detached tool ${tool.name}`, `已卸载工具 ${tool.name}`));
      } else {
        await attachTool(selectedAgentId, tool.id);
        setStatus(t(`Attached tool ${tool.name}`, `已挂载工具 ${tool.name}`));
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
      setError(t("Select an agent first.", "请先选择智能体。"));
      return;
    }
    if (selectedAgentArchived) {
      setError(t("Archived agents cannot run tool probe. Restore first.", "归档智能体不可运行工具探测，请先恢复。"));
      return;
    }

    const input = toolProbeInput.trim();
    if (!input) {
      setError(t("Tool probe input cannot be empty.", "工具探测输入不能为空。"));
      return;
    }
    const parsedTimeoutSeconds = parsePositiveFloat(runtimeTimeoutSeconds);
    if (parsedTimeoutSeconds === null) {
      setError(t("Timeout must be a positive number.", "超时时间必须是正数。"));
      return;
    }
    const parsedRetryCount = parseRetryCount(runtimeRetryCount);
    if (parsedRetryCount === null) {
      setError(t("Retry count must be an integer between 0 and 5.", "重试次数必须是 0 到 5 之间的整数。"));
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
        timeout_seconds: parsedTimeoutSeconds,
        retry_count: parsedRetryCount,
      });
      setToolProbeResult(payload);
      setLastResult(payload.result || null);
      setStatus(
        t(
          `Tool probe completed: ${payload.tool_call_count} tool call(s), ${payload.tool_return_count} return(s).`,
          `工具探测完成：${payload.tool_call_count} 次工具调用，${payload.tool_return_count} 次工具返回。`,
        ),
      );
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
      setStatus(t("Agent persistent state refreshed.", "智能体持久化状态已刷新。"));
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
      <div className="kicker">{t("Merged Workspace", "合并工作区")}</div>
      <h1 className="section-title">{t("Agent Studio", "智能体工作台")}</h1>

      <div className="studio-layout">
        <aside className="card studio-panel">
          <h3>{t("Inspector", "检查面板")}</h3>

          <div className="form-grid">
            <label className="field">
              <span>{t("New agent name", "新建智能体名称")}</span>
              <input className="input" value={createName} onChange={(e) => setCreateName(e.target.value)} />
            </label>
            <label className="field">
              <span>{t("Model", "模型")}</span>
              <select className="input" value={createModel} onChange={(e) => setCreateModel(e.target.value)}>
                <option value="">{t("Select model", "选择模型")}</option>
                {models.map((item) => (
                  <option key={item.key} value={item.key}>
                    {modelOptionLabel(item)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t("Prompt", "提示词")}</span>
              <select className="input" value={createPromptKey} onChange={(e) => setCreatePromptKey(e.target.value)}>
                {prompts.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t("Persona", "Persona")}</span>
              <select className="input" value={createPersonaKey} onChange={(e) => setCreatePersonaKey(e.target.value)}>
                {personas.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t("Embedding", "向量模型")}</span>
              <select className="input" value={createEmbedding} onChange={(e) => setCreateEmbedding(e.target.value)}>
                <option value="">{t("Use server default", "使用服务端默认值")}</option>
                {embeddings.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t("Temperature (optional)", "Temperature（可选）")}</span>
              <input
                className="input"
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={createTemperature}
                onChange={(e) => setCreateTemperature(e.target.value)}
                placeholder={t("Use model default", "使用模型默认值")}
              />
            </label>
            <label className="field">
              <span>{t("Top P (optional)", "Top P（可选）")}</span>
              <input
                className="input"
                type="number"
                min={0.01}
                max={1}
                step={0.05}
                value={createTopP}
                onChange={(e) => setCreateTopP(e.target.value)}
                placeholder={t("Use model default", "使用模型默认值")}
              />
            </label>
          </div>

          <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="button" onClick={onCreateAgent} disabled={busy || loading}>
              {busy ? t("Creating...", "创建中...") : t("Create Agent", "创建智能体")}
            </button>
            <button className="button muted" onClick={() => void refreshAgentList()} disabled={busy || loading}>
              {t("Refresh Agents", "刷新智能体列表")}
            </button>
            <button className="button muted" onClick={() => void onReloadModels()} disabled={busy || loading}>
              {t("Reload Models", "重新加载模型")}
            </button>
          </div>

          <hr className="studio-divider" />

          <label className="field">
            <span>{t("Existing agents", "已有智能体")}</span>
            <label className="field" style={{ marginTop: 6 }}>
              <span>
                <input
                  type="checkbox"
                  checked={includeArchivedAgents}
                  onChange={(event) => setIncludeArchivedAgents(event.target.checked)}
                  style={{ marginRight: 8 }}
                />
                {t("Include archived agents", "显示已归档智能体")}
              </span>
            </label>
            <select className="input" value={selectedAgentId} onChange={(e) => setSelectedAgentId(e.target.value)}>
              <option value="">{t("Select agent", "选择智能体")}</option>
              {agents.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.model}){item.archived ? t(" [Archived]", " [已归档]") : ""}
                </option>
              ))}
            </select>
          </label>

          {selectedAgentInfo ? (
            <div className="code" style={{ marginTop: 8 }}>
              {t("ID", "ID")}: {shortId(selectedAgentInfo.id)}
              {"\n"}
              {t("Status", "状态")}: {selectedAgentInfo.archived ? t("Archived", "已归档") : t("Active", "活跃")}
              {"\n"}
              {t("Created", "创建时间")}: {formatTimestamp(selectedAgentInfo.created_at, locale)}
              {"\n"}
              {t("Last interaction", "最近交互")}: {formatTimestamp(selectedAgentInfo.last_interaction_at || selectedAgentInfo.last_updated_at, locale)}
            </div>
          ) : null}

          <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="button muted" onClick={() => void onPullExistingInfo()} disabled={!selectedAgentId || busy}>
              {t("Pull Existing Info", "拉取已有信息")}
            </button>
            <button className="button muted" onClick={() => void onRefreshPersistent()} disabled={!selectedAgentId || busy}>
              {t("Refresh Selected", "刷新当前智能体")}
            </button>
          </div>

          <div className="toolbar" style={{ marginTop: 8 }}>
            <button
              className="button muted"
              onClick={() => void onArchiveAgent()}
              disabled={!selectedAgentId || busy || selectedAgentArchived}
            >
              {t("Archive Agent", "归档智能体")}
            </button>
            <button
              className="button muted"
              onClick={() => void onRestoreAgent()}
              disabled={!selectedAgentId || busy || !selectedAgentArchived}
            >
              {t("Restore Agent", "恢复智能体")}
            </button>
            <button
              className="button danger"
              onClick={() => void onPurgeAgent()}
              disabled={!selectedAgentId || busy || !selectedAgentArchived}
            >
              {t("Purge Agent", "彻底删除")}
            </button>
          </div>

          <p className="muted" style={{ marginTop: 10 }}>
            {t("Selected", "当前")}: {selectedAgentName || t("none", "无")}
            {selectedAgentArchived ? t(" (archived)", "（已归档）") : ""}
          </p>
          <p className="muted">{t("Conversation rows", "对话条数")}: {historyCount}</p>

          {agentDetails ? (
            <>
              <div className="studio-tabs">
                <button className={inspectorTab === "model" ? "tab-active" : "tab-item"} onClick={() => setInspectorTab("model")}>
                  {t("Model", "模型")}
                </button>
                <button className={inspectorTab === "prompt" ? "tab-active" : "tab-item"} onClick={() => setInspectorTab("prompt")}>
                  {t("Prompt", "提示词")}
                </button>
                <button className={inspectorTab === "tools" ? "tab-active" : "tab-item"} onClick={() => setInspectorTab("tools")}>
                  {t("Tools", "工具")}
                </button>
              </div>

              {inspectorTab === "model" ? (
                <div className="studio-stack">
                  <div className="field">
                    <span>{t("Agent model override", "智能体模型覆盖")}</span>
                    <select className="input" value={modelEditValue} onChange={(e) => setModelEditValue(e.target.value)}>
                      <option value="">{t("Select model", "选择模型")}</option>
                      {models.map((item) => (
                        <option key={item.key} value={item.key}>
                          {modelOptionLabel(item)}
                        </option>
                      ))}
                    </select>
                    <button className="button" onClick={() => void onApplyModel()} disabled={modelBusy || !selectedAgentId || !modelEditValue || selectedAgentArchived}>
                      {modelBusy ? t("Applying...", "应用中...") : t("Apply Model", "应用模型")}
                    </button>
                  </div>
                  <div className="code">
                    {t("Type", "类型")}: {agentDetails.agent_type || t("unknown", "未知")}
                    {"\n"}
                    {t("Context window", "上下文窗口")}: {agentDetails.context_window_limit ?? "N/A"}
                    {"\n"}
                    {t("Last interaction", "最近交互")}: {formatTimestamp(agentDetails.last_interaction_at || agentDetails.last_updated_at, locale)}
                  </div>
                  {agentDetails.llm_config ? (
                    <div className="code">{JSON.stringify(agentDetails.llm_config, null, 2)}</div>
                  ) : null}
                </div>
              ) : null}

              {inspectorTab === "prompt" ? (
                <div className="studio-stack">
                  <div className="toolbar prompt-action-row">
                    <button className="prompt-action-button" disabled={selectedAgentArchived} onClick={() => openEditor("system", agentDetails.system || "")}>{t("Edit System Prompt", "编辑 System Prompt")}</button>
                    <button className="prompt-action-button" disabled={selectedAgentArchived} onClick={() => openEditor("persona", personaValue)}>{t("Edit Persona", "编辑 Persona")}</button>
                    <button className="prompt-action-button" disabled={selectedAgentArchived} onClick={() => openEditor("human", humanValue)}>{t("Edit Human", "编辑 Human")}</button>
                    <button
                      className="prompt-action-button"
                      onClick={() => void refreshRevisionHistory(selectedAgentId)}
                      disabled={!selectedAgentId || revisionLoading || selectedAgentArchived}
                    >
                      {revisionLoading ? t("Refreshing...", "刷新中...") : t("Refresh Timeline", "刷新时间线")}
                    </button>
                  </div>
                  <div className="code">{agentDetails.system || t("No system prompt.", "暂无 system prompt。")}</div>

                  <div className="card" style={{ padding: 10 }}>
                    <div className="toolbar" style={{ justifyContent: "space-between" }}>
                      <strong>{t("Revision Timeline", "修订时间线")}</strong>
                      <span className="muted">{revisionHistory.length} {t("record(s)", "条记录")}</span>
                    </div>
                    {revisionHistory.length === 0 ? (
                      <p className="muted" style={{ marginTop: 8 }}>
                        {t("No prompt/persona revisions recorded yet for this agent.", "该智能体尚无 prompt/persona 修订记录。")}
                      </p>
                    ) : (
                      <div className="studio-stack" style={{ marginTop: 8, maxHeight: 320, overflowY: "auto" }}>
                        {revisionHistory.map((record) => (
                          <div className="card revision-item" style={{ padding: 10 }} key={record.revision_id}>
                            <div className="toolbar" style={{ justifyContent: "space-between" }}>
                              <strong>{record.field}</strong>
                              <span className="muted">{formatTimestamp(record.recorded_at, locale)}</span>
                            </div>
                            <p className="muted" style={{ marginTop: 6 }}>
                              {t("source", "来源")}: {record.source} | {t("delta", "变更")}: {record.delta_length >= 0 ? `+${record.delta_length}` : record.delta_length}
                            </p>
                            <details style={{ marginTop: 8 }}>
                              <summary>{t("View before/after preview", "查看前后预览")}</summary>
                              <div className="code" style={{ marginTop: 8 }}>
                                [{t("before", "变更前")}]
                                {"\n"}
                                {record.before_preview || t("(empty)", "（空）")}
                                {"\n\n"}
                                [{t("after", "变更后")}]
                                {"\n"}
                                {record.after_preview || t("(empty)", "（空）")}
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
                      placeholder={t("Search tools", "搜索工具")}
                      onChange={(e) => setToolSearch(e.target.value)}
                    />
                    <button className="button muted" onClick={() => void refreshToolCatalog(selectedAgentId)} disabled={!selectedAgentId}>
                      {t("Refresh", "刷新")}
                    </button>
                  </div>
                  {displayToolCatalog.length === 0 ? (
                    <p className="muted">{t("No tools found.", "未找到工具。")}</p>
                  ) : (
                    <div className="studio-stack">
                      {displayToolCatalog.map((tool) => {
                        const isAttached = Boolean(tool.attached_to_agent);
                        const preview = summarizeDescription(
                          tool.description || "",
                          t("No description.", "暂无描述。"),
                        );
                        return (
                          <div key={tool.id} className="card tool-card" style={{ padding: 10 }}>
                            <div className="tool-card-header">
                              <strong className="tool-card-name">{tool.name}</strong>
                              <button
                                className={`button tool-action-button ${isAttached ? "danger" : "success"}`}
                                onClick={() => void onToggleTool(tool)}
                                disabled={toolBusyId === tool.id || !selectedAgentId || selectedAgentArchived}
                              >
                                {toolBusyId === tool.id
                                  ? t("Working...", "处理中...")
                                  : isAttached
                                    ? t("Detach", "卸载")
                                    : t("Attach", "挂载")}
                              </button>
                            </div>
                            <div className="toolbar tool-card-actions">
                              <button
                                className="button muted tool-detail-button"
                                title={t("View full details", "查看完整详情")}
                                onClick={() => setToolDetailTool(tool)}
                              >
                                {t("View details", "查看详情")}
                              </button>
                            </div>
                            <p className="muted tool-card-description" style={{ marginTop: 8 }}>{preview}</p>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div className="card" style={{ padding: 10 }}>
                    <h4 style={{ margin: 0 }}>{t("Tool Probe (Phase-2)", "工具探测（Phase-2）")}</h4>
                    <p className="muted" style={{ marginTop: 8 }}>
                      {t(
                        "Sends a runtime message and reports detected tool calls/returns.",
                        "发送运行时消息，并输出检测到的工具调用/返回统计。",
                      )}
                    </p>
                    <p className="muted" style={{ marginTop: 8 }}>
                      {t(
                        "Uses the shared Agent Studio timeout and retry controls from the Chat panel.",
                        "会使用聊天面板中的共享超时与重试控制。",
                      )}
                    </p>
                    <label className="field" style={{ marginTop: 8 }}>
                      <span>{t("Probe input", "探测输入")}</span>
                      <textarea
                        className="input"
                        style={{ minHeight: 84, resize: "vertical" }}
                        value={toolProbeInput}
                        onChange={(e) => setToolProbeInput(e.target.value)}
                      />
                    </label>
                    <label className="field" style={{ marginTop: 8 }}>
                      <span>{t("Expected tool name (optional)", "期望工具名（可选）")}</span>
                      <input
                        className="input"
                        value={toolProbeExpected}
                        onChange={(e) => setToolProbeExpected(e.target.value)}
                        placeholder={t("e.g. search_documents", "例如 search_documents")}
                      />
                    </label>
                    <div className="toolbar" style={{ marginTop: 8 }}>
                      <button
                        className="button"
                        onClick={() => void onRunToolProbe()}
                        disabled={!selectedAgentId || toolProbeBusy || selectedAgentArchived}
                      >
                        {toolProbeBusy ? t("Running...", "运行中...") : t("Run Tool Probe", "运行工具探测")}
                      </button>
                    </div>
                    {toolProbeResult ? (
                      <div className="code" style={{ marginTop: 8 }}>
                        {t("tool_call_count", "tool_call_count")}: {toolProbeResult.tool_call_count}
                        {"\n"}
                        {t("tool_return_count", "tool_return_count")}: {toolProbeResult.tool_return_count}
                        {"\n"}
                        {t("expected_tool_name", "expected_tool_name")}: {toolProbeResult.expected_tool_name || t("(none)", "（无）")}
                        {"\n"}
                        {t("expected_tool_matched", "expected_tool_matched")}: {String(toolProbeResult.expected_tool_matched)}
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </>
          ) : null}
        </aside>

        <main className="card studio-panel">
          <h3>{t("Chat", "对话")}</h3>
          <div className="chat-scroll" ref={chatScrollRef}>
            {chatHistory.length === 0 ? (
              <p className="muted">{t("Send a message or use Pull Existing Info to hydrate history.", "发送消息，或使用拉取已有信息来载入历史。")}</p>
            ) : (
              chatHistory.map((entry) => (
                <div key={entry.id} className={`chat-row ${entry.role === "user" ? "user" : "assistant"}`}>
                  <div className="chat-bubble">
                    <div className="chat-meta">
                      <span>{entry.role === "user" ? t("You", "你") : t("Assistant", "助手")}</span>
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

          <div className="form-grid" style={{ marginTop: 12 }}>
            <label className="field">
              <span>{t("Timeout (seconds)", "超时时间（秒）")}</span>
              <input
                className="input"
                type="number"
                min={5}
                max={600}
                step={1}
                value={runtimeTimeoutSeconds}
                onChange={(e) => setRuntimeTimeoutSeconds(e.target.value)}
                disabled={chatBusy || toolProbeBusy}
              />
            </label>
            <label className="field">
              <span>{t("Retry Count", "重试次数")}</span>
              <input
                className="input"
                type="number"
                min={0}
                max={5}
                step={1}
                value={runtimeRetryCount}
                onChange={(e) => setRuntimeRetryCount(e.target.value)}
                disabled={chatBusy || toolProbeBusy}
              />
            </label>
          </div>
          <p className="muted" style={{ marginTop: 8 }}>
            {t(
              "These settings apply to Chat and Tool Probe. Set retry count to 0 to disable retries.",
              "这些设置会同时作用于聊天与工具探测。将重试次数设为 0 即禁用重试。",
            )}
          </p>
          <div className="toolbar" style={{ marginTop: 12 }}>
            <textarea
              className="input"
              style={{ minHeight: 82, resize: "vertical", flex: 1 }}
              placeholder={t("Type a message (Enter to send)", "输入消息（回车发送）")}
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void onSendMessage();
                }
              }}
            />
            <button className="button" onClick={() => void onSendMessage()} disabled={chatBusy || !selectedAgentId || selectedAgentArchived}>
              {chatBusy ? t("Sending...", "发送中...") : t("Send", "发送")}
            </button>
          </div>
        </main>

        <aside className="card studio-panel">
          <h3>{t("Execution Trace", "执行轨迹")}</h3>
          {lastLatencyMs !== null ? <p className="muted">{t("Last response latency", "最近响应延迟")}: {formatLatency(lastLatencyMs)}</p> : null}
          <div className="toolbar" style={{ marginTop: 8 }}>
            <button
              className={timelineFilter === "all" ? "button" : "button muted"}
              onClick={() => setTimelineFilter("all")}
            >
              {t("All", "全部")}
            </button>
            <button
              className={timelineFilter === "assistant" ? "button" : "button muted"}
              onClick={() => setTimelineFilter("assistant")}
            >
              {t("Assistant", "助手")}
            </button>
            <button
              className={timelineFilter === "tool" ? "button" : "button muted"}
              onClick={() => setTimelineFilter("tool")}
            >
              {t("Tool", "工具")}
            </button>
            <button
              className={timelineFilter === "reasoning" ? "button" : "button muted"}
              onClick={() => setTimelineFilter("reasoning")}
            >
              {t("Reasoning", "推理")}
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
            <p className="muted">{t("No runtime steps yet.", "暂无运行步骤。")}</p>
          )}

          {lastResult ? (
            <div className="studio-stack" style={{ marginTop: 10 }}>
              <h4 style={{ margin: 0 }}>{t("Human Memory Diff", "Human 记忆差异")}</h4>
              <div className="code memory-diff" dangerouslySetInnerHTML={{ __html: highlightDiff(humanBefore, humanAfter) }} />
            </div>
          ) : null}

          <hr className="studio-divider" />

          <div className="toolbar" style={{ justifyContent: "space-between" }}>
            <h4 style={{ margin: 0 }}>{t("Raw Prompt Context", "原始 Prompt 上下文")}</h4>
            <button className="button muted" onClick={() => void onToggleRawPrompt()}>
              {showRawPrompt ? t("Hide", "隐藏") : t("Show", "显示")}
            </button>
          </div>
          {showRawPrompt ? (
            rawPromptLoading ? (
              <p className="muted">{t("Loading raw prompt...", "加载原始 prompt 中...")}</p>
            ) : (
              <div className="studio-stack">
                {rawPromptMessages.length === 0 ? (
                  <p className="muted">{t("No prompt payload loaded.", "未加载到 prompt 载荷。")}</p>
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
            <h4 style={{ margin: 0 }}>{t("Persistent State", "持久化状态")}</h4>
            <button className="button muted" onClick={() => void onRefreshPersistent()} disabled={!selectedAgentId || busy}>
              {t("Refresh", "刷新")}
            </button>
          </div>
          <div className="toolbar" style={{ marginTop: 8 }}>
            <label className="field" style={{ width: 150 }}>
              <span>{t("History limit", "历史上限")}</span>
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
              {t("Summary", "摘要")}
            </button>
            <button className={persistentTab === "memory" ? "tab-active" : "tab-item"} onClick={() => setPersistentTab("memory")}>
              {t("Memory", "记忆")}
            </button>
            <button className={persistentTab === "history" ? "tab-active" : "tab-item"} onClick={() => setPersistentTab("history")}>
              {t("History", "历史")}
            </button>
          </div>

          {persistentTab === "summary" && persistentState ? (
            <div className="code" style={{ marginTop: 8 }}>
              {t("Agent", "智能体")}: {persistentState.agent?.id || "N/A"}
              {"\n"}
              {t("Name", "名称")}: {persistentState.agent?.name || "N/A"}
              {"\n"}
              {t("Model", "模型")}: {persistentState.agent?.model || "N/A"}
              {"\n"}
              {t("History rows", "历史条数")}: {persistentState.conversation_history?.displayed || 0} / {persistentState.conversation_history?.total_persisted || 0}
              {"\n"}
              {t("Counts by type", "按类型统计")}:
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
                      <button className="button muted" disabled={selectedAgentArchived} onClick={() => openEditor("persona", block.value)}>{t("Edit", "编辑")}</button>
                    ) : null}
                    {block.label === "human" ? (
                      <button className="button muted" disabled={selectedAgentArchived} onClick={() => openEditor("human", block.value)}>{t("Edit", "编辑")}</button>
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
                    <span className="muted">{formatTimestamp(item.created_at, locale)}</span>
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
            <h3 style={{ marginTop: 0 }}>{t("Edit", "编辑")} {editorKind}</h3>
            <textarea
              className="input"
              style={{ minHeight: 260, resize: "vertical" }}
              value={editorValue}
              onChange={(e) => setEditorValue(e.target.value)}
            />
            <div className="toolbar" style={{ marginTop: 10, justifyContent: "flex-end" }}>
              <button className="button muted" onClick={closeEditor} disabled={editorBusy}>
                {t("Cancel", "取消")}
              </button>
              <button className="button" onClick={() => void onSaveEditor()} disabled={editorBusy}>
                {editorBusy ? t("Saving...", "保存中...") : t("Save", "保存")}
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
          aria-label={t(`Tool details: ${toolDetailTool.name}`, `工具详情：${toolDetailTool.name}`)}
        >
          <div className="editor-card tool-detail-card" onClick={(event) => event.stopPropagation()}>
            <div className="tool-detail-header">
              <div>
                <h3 style={{ margin: 0 }}>{toolDetailTool.name}</h3>
                <div className="tool-detail-meta">
                  <span className="tool-detail-badge">{toolDetailTool.attached_to_agent ? t("Attached", "已挂载") : t("Not Attached", "未挂载")}</span>
                  <span className="tool-detail-badge">{t("Type", "类型")}: {toolDetailTool.tool_type || t("unknown", "未知")}</span>
                  <span className="tool-detail-badge">{t("Source", "来源")}: {toolDetailTool.source_type || t("unknown", "未知")}</span>
                </div>
              </div>
              <button className="button muted" onClick={() => setToolDetailTool(null)}>
                {t("Close (Esc)", "关闭（Esc）")}
              </button>
            </div>

            {(() => {
              const parsed = parseToolExamples(
                toolDetailTool.description || "",
                t("No description.", "暂无描述。"),
                t("No overview provided.", "未提供概述。"),
              );
              return (
                <>
                  <p className="tool-detail-overview">{parsed.overview}</p>
                  {parsed.examples.length > 0 ? (
                    <>
                      <div className="tool-detail-section-title">{t("Examples", "示例")}</div>
                      {parsed.examples.map((example, idx) => (
                        <pre className="code tool-detail-code" key={`${toolDetailTool.id}-example-${idx}`}>
                          {example}
                        </pre>
                      ))}
                    </>
                  ) : (
                    <>
                      <div className="tool-detail-section-title">{t("Full Description", "完整说明")}</div>
                      <pre className="code tool-detail-code">{toolDetailTool.description || t("No description.", "暂无描述。")}</pre>
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
          <h3>{t("Status", "状态")}</h3>
          <p className="muted">{status}</p>
        </div>
      ) : null}

      {error ? (
        <div className="card" style={{ marginTop: 12, borderColor: "#fecaca" }}>
          <h3>{t("Error", "错误")}</h3>
          <p className="muted">{error}</p>
        </div>
      ) : null}
    </section>
  );
}
