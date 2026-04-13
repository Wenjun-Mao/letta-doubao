export const DEV_UI_BASE_URL = process.env.NEXT_PUBLIC_DEV_UI_BASE_URL || "http://127.0.0.1:8284";
const DEFAULT_GET_CACHE_TTL_MS = 45_000;

type CacheEntry = {
  expiresAt: number;
  value: unknown;
};

const GET_RESPONSE_CACHE = new Map<string, CacheEntry>();

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  bypassCache?: boolean;
  cacheTtlMs?: number;
};

export type OptionEntry = {
  key: string;
  label: string;
  description: string;
  available?: boolean;
  is_default?: boolean;
};

export type AgentListItem = {
  id: string;
  name: string;
  model: string;
  created_at: string;
  last_updated_at: string;
  last_interaction_at: string;
};

export type AgentDetails = {
  id: string;
  name: string;
  agent_type?: string;
  model: string;
  embedding?: string | null;
  created_at?: string;
  last_updated_at?: string;
  last_interaction_at?: string;
  llm_config?: unknown;
  embedding_config?: unknown;
  tool_rules?: unknown;
  context_window_limit?: number | null;
  system: string;
  tools: Record<string, string>;
  memory: Record<string, string>;
};

export type PersistentState = {
  source?: string;
  agent?: {
    id: string;
    name: string;
    agent_type: string;
    model: string;
    embedding?: string | null;
    created_at?: string;
    last_updated_at?: string;
    context_window_limit?: number | null;
    tool_rules?: string;
  };
  memory_blocks: Array<{
    label: string;
    value: string;
    description: string;
    limit: number | null;
  }>;
  tools?: Array<{
    id: string;
    name: string;
    description: string;
  }>;
  conversation_history: {
    total_persisted: number;
    displayed: number;
    limit?: number;
    counts_by_type?: Record<string, number>;
    items: Array<{
      id: string;
      created_at: string;
      role: string;
      message_type: string;
      content: string;
      name?: string | null;
      tool_arguments?: string | null;
    }>;
  };
};

export type ChatStep = {
  type: string;
  content?: string;
  name?: string;
  status?: string;
  arguments?: string;
  tool_arguments?: string;
  message_type?: string;
};

export type ChatResult = {
  total_steps: number;
  sequence: ChatStep[];
  memory_diff: {
    old: Record<string, string>;
    new: Record<string, string>;
  };
};

export type PlatformTool = {
  id: string;
  name: string;
  description: string;
  tool_type: string;
  source_type: string;
  created_at: string;
  last_updated_at: string;
  tags: string[];
  attached_to_agent?: boolean;
};

export type PlatformToolTestInvokeResult = {
  agent_id: string;
  input: string;
  expected_tool_name?: string | null;
  expected_tool_matched?: boolean | null;
  tool_call_count: number;
  tool_return_count: number;
  result: ChatResult;
};

export type PromptPersonaRevisionRecord = {
  revision_id: string;
  recorded_at: string;
  agent_id: string;
  field: "system" | "persona" | "human";
  source: string;
  before: string;
  after: string;
  before_preview: string;
  after_preview: string;
  before_length: number;
  after_length: number;
  delta_length: number;
};

export type PlatformRunRecord = {
  run_id: string;
  run_type: string;
  status: string;
  command: string[];
  created_at: string;
  started_at: string;
  finished_at: string;
  exit_code: number | null;
  log_file: string;
  cancel_requested: boolean;
  output_tail: string[];
  error: string;
  artifacts?: PlatformArtifact[];
};

export type PlatformArtifact = {
  artifact_id: string;
  type: string;
  path: string;
  exists: boolean;
  size_bytes: number;
};

function cacheKey(path: string): string {
  return path;
}

export function invalidateApiCache(prefixes: string[] = []): void {
  if (prefixes.length === 0) {
    GET_RESPONSE_CACHE.clear();
    return;
  }

  const normalized = prefixes.filter((prefix) => prefix.trim().length > 0);
  if (normalized.length === 0) {
    GET_RESPONSE_CACHE.clear();
    return;
  }

  for (const key of Array.from(GET_RESPONSE_CACHE.keys())) {
    if (normalized.some((prefix) => key.startsWith(prefix))) {
      GET_RESPONSE_CACHE.delete(key);
    }
  }
}

function invalidateAgentScope(agentId: string): void {
  if (!agentId.trim()) {
    invalidateApiCache(["/api/agents", "/api/platform/tools", "/api/platform/agents"]);
    return;
  }

  const id = agentId.trim();
  invalidateApiCache([
    "/api/agents",
    `/api/agents/${id}/details`,
    `/api/agents/${id}/persistent_state`,
    `/api/agents/${id}/raw_prompt`,
    `/api/platform/agents/${id}`,
    "/api/platform/metadata/prompts-personas/revisions",
    "/api/platform/tools",
  ]);
}

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method || "GET";
  const shouldUseCache = method === "GET" && !options.bypassCache;
  const resolvedCacheKey = cacheKey(path);

  if (shouldUseCache) {
    const cached = GET_RESPONSE_CACHE.get(resolvedCacheKey);
    if (cached && cached.expiresAt > Date.now()) {
      return cached.value as T;
    }
    if (cached) {
      GET_RESPONSE_CACHE.delete(resolvedCacheKey);
    }
  }

  const response = await fetch(`${DEV_UI_BASE_URL}${path}`, {
    method,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `Request failed ${response.status}: ${path}`);
  }

  const payload = (await response.json()) as T;
  if (shouldUseCache) {
    GET_RESPONSE_CACHE.set(resolvedCacheKey, {
      value: payload,
      expiresAt: Date.now() + (options.cacheTtlMs ?? DEFAULT_GET_CACHE_TTL_MS),
    });
  }

  return payload;
}

export function fetchMigrationStatus() {
  return requestJson<{
    migration_mode: string;
    platform_api_enabled: boolean;
    legacy_api_enabled: boolean;
    strict_capabilities: boolean;
  }>("/api/platform/migration-status", { cacheTtlMs: 15_000 });
}

export function fetchCapabilities() {
  return requestJson<{
    enabled: boolean;
    strict_mode: boolean;
    missing_required: string[];
    runtime: Record<string, boolean>;
    control: Record<string, boolean>;
  }>("/api/platform/capabilities", { cacheTtlMs: 15_000 });
}

export function fetchOptions() {
  return requestJson<{
    models: OptionEntry[];
    embeddings: OptionEntry[];
    prompts: OptionEntry[];
    defaults: {
      model: string;
      prompt_key: string;
      embedding: string;
    };
  }>("/api/options", { cacheTtlMs: 60_000 });
}

export function listAgents(limit = 200, includeLastInteraction = false) {
  const params = new URLSearchParams();
  params.set("limit", `${limit}`);
  if (includeLastInteraction) {
    params.set("include_last_interaction", "true");
  }

  return requestJson<{
    total: number;
    items: AgentListItem[];
  }>(`/api/agents?${params.toString()}`, { cacheTtlMs: 15_000 });
}

export function createAgent(payload: {
  name: string;
  model: string;
  prompt_key: string;
  embedding?: string | null;
}) {
  return requestJson<{
    id: string;
    name: string;
    model: string;
    embedding?: string | null;
    prompt_key: string;
  }>("/api/agents", {
    method: "POST",
    body: payload,
  }).then((created) => {
    invalidateApiCache(["/api/agents", "/api/platform/tools", "/api/options"]);
    return created;
  });
}

export function getAgentDetails(agentId: string) {
  return requestJson<AgentDetails>(`/api/agents/${agentId}/details`, { cacheTtlMs: 20_000 });
}

export function getPersistentState(agentId: string, limit = 120) {
  return requestJson<PersistentState>(`/api/agents/${agentId}/persistent_state?limit=${limit}`, { cacheTtlMs: 20_000 });
}

export function getRawPrompt(agentId: string) {
  return requestJson<{ messages: Array<{ role: string; content: string }> }>(`/api/agents/${agentId}/raw_prompt`, {
    cacheTtlMs: 20_000,
  });
}

export function sendChat(agentId: string, message: string) {
  return requestJson<ChatResult>("/api/chat", {
    method: "POST",
    body: {
      agent_id: agentId,
      message,
    },
  }).then((result) => {
    invalidateAgentScope(agentId);
    return result;
  });
}

export function fetchPromptPersonaMetadata() {
  return requestJson<{
    defaults: {
      prompt_key: string;
      persona_key: string;
    };
    prompts: Array<{
      key: string;
      label: string;
      description: string;
      preview: string;
      length: number;
    }>;
    personas: Array<{
      key: string;
      preview: string;
      length: number;
    }>;
  }>("/api/platform/metadata/prompts-personas", { cacheTtlMs: 60_000 });
}

export function fetchPromptPersonaRevisions(agentId: string, field = "", limit = 80) {
  const params = new URLSearchParams();
  if (agentId.trim()) {
    params.set("agent_id", agentId.trim());
  }
  if (field.trim()) {
    params.set("field", field.trim());
  }
  params.set("limit", `${Math.max(1, Math.min(500, limit))}`);
  return requestJson<{
    total: number;
    limit: number;
    agent_id: string | null;
    field: string | null;
    items: PromptPersonaRevisionRecord[];
  }>(`/api/platform/metadata/prompts-personas/revisions?${params.toString()}`, { cacheTtlMs: 10_000 });
}

export function updateSystemPrompt(agentId: string, system: string) {
  return requestJson<{ system_after: string; system_before: string }>(`/api/platform/agents/${agentId}/system`, {
    method: "PATCH",
    body: { system },
  }).then((payload) => {
    invalidateAgentScope(agentId);
    return payload;
  });
}

export function updateAgentModel(agentId: string, model: string) {
  return requestJson<{ model_after: string; model_before: string }>(`/api/platform/agents/${agentId}/model`, {
    method: "PATCH",
    body: { model },
  }).then((payload) => {
    invalidateAgentScope(agentId);
    return payload;
  });
}

export function updateCoreMemoryBlock(agentId: string, blockLabel: string, value: string) {
  return requestJson<{ value_before: string; value_after: string }>(
    `/api/platform/agents/${agentId}/core-memory/blocks/${blockLabel}`,
    {
      method: "PATCH",
      body: { value },
    },
  ).then((payload) => {
    invalidateAgentScope(agentId);
    return payload;
  });
}

export function listTools(search = "", limit = 200, agentId = "") {
  const params = new URLSearchParams();
  params.set("limit", `${limit}`);
  if (search.trim()) {
    params.set("search", search.trim());
  }
  if (agentId.trim()) {
    params.set("agent_id", agentId.trim());
  }

  return requestJson<{
    total: number;
    items: PlatformTool[];
  }>(`/api/platform/tools?${params.toString()}`, { cacheTtlMs: 20_000 });
}

export function testInvokeTool(payload: {
  agent_id: string;
  input: string;
  expected_tool_name?: string;
  override_model?: string;
  override_system?: string;
}) {
  return requestJson<PlatformToolTestInvokeResult>("/api/platform/tools/test-invoke", {
    method: "POST",
    body: payload,
  }).then((result) => {
    invalidateAgentScope(payload.agent_id || "");
    return result;
  });
}

export function attachTool(agentId: string, toolId: string) {
  return requestJson(`/api/platform/agents/${agentId}/tools/attach/${toolId}`, {
    method: "PATCH",
  }).then((payload) => {
    invalidateAgentScope(agentId);
    return payload;
  });
}

export function detachTool(agentId: string, toolId: string) {
  return requestJson(`/api/platform/agents/${agentId}/tools/detach/${toolId}`, {
    method: "PATCH",
  }).then((payload) => {
    invalidateAgentScope(agentId);
    return payload;
  });
}

export function listTestRuns() {
  return requestJson<{ items: PlatformRunRecord[] }>("/api/platform/test-runs", { cacheTtlMs: 3_000 });
}

export function createTestRun(payload: {
  run_type: string;
  model?: string;
  embedding?: string;
  rounds?: number;
  config_path?: string;
}) {
  return requestJson<PlatformRunRecord>("/api/platform/test-runs", {
    method: "POST",
    body: payload,
  }).then((record) => {
    invalidateApiCache(["/api/platform/test-runs"]);
    return record;
  });
}

export function getTestRun(runId: string) {
  return requestJson<PlatformRunRecord>(`/api/platform/test-runs/${runId}`, { cacheTtlMs: 3_000 });
}

export function cancelTestRun(runId: string) {
  return requestJson<PlatformRunRecord>(`/api/platform/test-runs/${runId}/cancel`, {
    method: "POST",
  }).then((record) => {
    invalidateApiCache(["/api/platform/test-runs"]);
    return record;
  });
}

export function listRunArtifacts(runId: string) {
  return requestJson<{
    run_id: string;
    items: PlatformArtifact[];
  }>(`/api/platform/test-runs/${runId}/artifacts`, { cacheTtlMs: 5_000 });
}

export function readRunArtifact(runId: string, artifactId: string, maxLines = 400) {
  return requestJson<{
    run_id: string;
    artifact: PlatformArtifact;
    content: string;
    truncated: boolean;
    line_count: number;
  }>(`/api/platform/test-runs/${runId}/artifacts/${artifactId}?max_lines=${maxLines}`, { cacheTtlMs: 5_000 });
}
