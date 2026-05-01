export const AGENT_PLATFORM_API_BASE_URL = process.env.NEXT_PUBLIC_AGENT_PLATFORM_API_BASE_URL || "http://127.0.0.1:8284";
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

export type Scenario = "chat" | "comment" | "label";
export type CommentingTaskShape = "classic" | "all_in_system" | "structured_output";
export type LabelingOutputMode = "strict_json_schema" | "json_schema" | "best_effort_prompt_json";
export type PlatformRunType = "platform_api_e2e_check" | "ade_mvp_smoke_e2e_check";

export type OptionEntry = {
  key: string;
  label: string;
  description: string;
  scenario?: Scenario | null;
  available?: boolean;
  is_default?: boolean;
  source_id?: string | null;
  source_label?: string | null;
  provider_model_id?: string | null;
  label_lab_available?: boolean | null;
  structured_output_mode?: LabelingOutputMode | null;
};

export type AgentListItem = {
  id: string;
  name: string;
  model: string;
  created_at: string;
  last_updated_at: string;
  last_interaction_at: string;
  archived: boolean;
};

export type AgentLifecycleRecord = {
  id: string;
  name: string;
  model: string;
  archived: boolean;
  archived_at?: string | null;
  updated_at: string;
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

export type CommentingGenerateResponse = {
  scenario: Scenario;
  model_key: string;
  source_id: string;
  source_label: string;
  provider_model_id: string;
  prompt_key: string;
  persona_key: string;
  model: string;
  content: string;
  provider: string;
  max_tokens: number;
  timeout_seconds: number;
  task_shape: CommentingTaskShape;
  cache_prompt: boolean;
  temperature: number;
  top_p: number;
  content_source?: string | null;
  selected_attempt: string;
  finish_reason?: string | null;
  usage: Record<string, unknown>;
  received_at?: string | null;
  raw_request: Record<string, unknown>;
  raw_reply: Record<string, unknown>;
};

export type LabelExtractionResult = Record<string, string[]>;

export type LabelingGenerateResponse = {
  scenario: Scenario;
  model_key: string;
  source_id: string;
  source_label: string;
  provider_model_id: string;
  prompt_key: string;
  schema_key: string;
  output_mode: LabelingOutputMode;
  selected_attempt: "primary" | "repair";
  result: LabelExtractionResult;
  finish_reason?: string | null;
  usage: Record<string, unknown>;
  received_at?: string | null;
  raw_request: Record<string, unknown>;
  raw_reply: Record<string, unknown>;
  validation_errors: string[];
  temperature: number;
  top_p: number;
};

export type LabelSchemaRecord = {
  key: string;
  label: string;
  description: string;
  schema: Record<string, unknown>;
  preview: string;
  archived: boolean;
  source_path: string;
  updated_at: string;
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
  managed?: boolean;
  read_only?: boolean;
  archived?: boolean;
  slug?: string | null;
};

export type PromptTemplateRecord = {
  kind: "prompt" | "persona";
  scenario: Scenario;
  key: string;
  label: string;
  description: string;
  content: string;
  preview: string;
  length: number;
  archived: boolean;
  source_path: string;
  updated_at: string;
  output_schema?: string | null;
};

export type ToolCenterItem = {
  slug?: string | null;
  tool_id: string;
  name: string;
  description: string;
  tool_type: string;
  source_type: string;
  tags: string[];
  managed: boolean;
  read_only: boolean;
  archived: boolean;
  source_path?: string | null;
  source_code?: string | null;
  created_at?: string;
  last_updated_at?: string;
  updated_at?: string | null;
  archived_at?: string | null;
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
    invalidateApiCache(["/api/v1/agents", "/api/v1/platform/tools", "/api/v1/platform/agents"]);
    return;
  }

  const id = agentId.trim();
  invalidateApiCache([
    "/api/v1/agents",
    `/api/v1/agents/${id}/details`,
    `/api/v1/agents/${id}/persistent_state`,
    `/api/v1/agents/${id}/raw_prompt`,
    `/api/v1/platform/agents/${id}`,
    "/api/v1/platform/metadata/prompts-personas/revisions",
    "/api/v1/platform/tools",
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

  const requestUrl = `${AGENT_PLATFORM_API_BASE_URL}${path}`;
  let response: Response;
  try {
    response = await fetch(requestUrl, {
      method,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : String(exc ?? "network request failed");
    throw new Error(`${method} ${path} failed: ${message}`);
  }

  if (!response.ok) {
    const payloadText = await response.text();
    if (payloadText) {
      try {
        const parsed = JSON.parse(payloadText) as { detail?: unknown };
        const detail = parsed?.detail;
        if (typeof detail === "string" && detail.trim()) {
          throw new Error(detail);
        }
        if (detail && typeof detail === "object" && !Array.isArray(detail)) {
          const detailObj = detail as Record<string, unknown>;
          const message = typeof detailObj.message === "string" ? detailObj.message.trim() : "";
          const validationErrors = Array.isArray(detailObj.validation_errors)
            ? detailObj.validation_errors
                .map((item) => String(item ?? "").trim())
                .filter((item) => item.length > 0)
            : [];
          if (message || validationErrors.length) {
            const combined = [message, ...validationErrors].filter((item) => item.length > 0).join("\n");
            throw new Error(combined);
          }
        }
      } catch (exc) {
        if (exc instanceof Error && !(exc instanceof SyntaxError)) {
          throw exc;
        }
      }
    }
    throw new Error(payloadText || `Request failed ${response.status}: ${path}`);
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

export function fetchCapabilities() {
  return requestJson<{
    enabled: boolean;
    strict_mode: boolean;
    missing_required: string[];
    runtime: Record<string, boolean>;
    control: Record<string, boolean>;
    sdk?: {
      messages_create_params: string[];
      agents_update_params: string[];
      blocks_update_params: string[];
    };
  }>("/api/v1/platform/capabilities", { cacheTtlMs: 15_000 });
}

export function fetchOptions(
  scenario: Scenario = "chat",
  options?: {
    refresh?: boolean;
    bypassCache?: boolean;
  },
) {
  const params = new URLSearchParams();
  params.set("scenario", scenario);
  if (options?.refresh) {
    params.set("refresh", "true");
  }

  const requestOptions: RequestOptions = {
    cacheTtlMs: 60_000,
  };
  if (options?.refresh) {
    requestOptions.bypassCache = options.bypassCache ?? true;
  } else if (options?.bypassCache !== undefined) {
    requestOptions.bypassCache = options.bypassCache;
  }

  return requestJson<{
    scenario: Scenario;
    models: OptionEntry[];
    embeddings: OptionEntry[];
    prompts: OptionEntry[];
    personas: OptionEntry[];
    schemas: OptionEntry[];
    defaults: {
      scenario: Scenario;
      model: string;
      prompt_key: string;
      persona_key: string;
      embedding: string;
      schema_key: string;
    };
    commenting?: {
      max_tokens: number;
      timeout_seconds: number;
      task_shape: CommentingTaskShape;
      cache_prompt: boolean;
      temperature: number;
      top_p: number;
    };
    labeling?: {
      max_tokens: number;
      timeout_seconds: number;
      repair_retry_count: number;
      temperature: number;
      top_p: number;
    };
    agent_studio?: {
      temperature?: number | null;
      top_p?: number | null;
    };
  }>(`/api/v1/options?${params.toString()}`, requestOptions);
}

export function listAgents(limit = 200, includeLastInteraction = false, includeArchived = false) {
  const params = new URLSearchParams();
  params.set("limit", `${limit}`);
  if (includeLastInteraction) {
    params.set("include_last_interaction", "true");
  }
  if (includeArchived) {
    params.set("include_archived", "true");
  }

  return requestJson<{
    total: number;
    items: AgentListItem[];
  }>(`/api/v1/agents?${params.toString()}`, { cacheTtlMs: 15_000 });
}

export function createAgent(payload: {
  scenario: Scenario;
  name: string;
  model: string;
  prompt_key: string;
  persona_key?: string;
  embedding?: string | null;
  temperature?: number;
  top_p?: number;
}) {
  return requestJson<{
    id: string;
    name: string;
    scenario: Scenario;
    model: string;
    embedding?: string | null;
    prompt_key: string;
    persona_key?: string;
  }>("/api/v1/agents", {
    method: "POST",
    body: payload,
  }).then((created) => {
    invalidateApiCache(["/api/v1/agents", "/api/v1/platform/tools", "/api/v1/options"]);
    return created;
  });
}

export function archiveAgent(agentId: string) {
  return requestJson<AgentLifecycleRecord>(`/api/v1/platform/agents/${agentId}/archive`, {
    method: "POST",
  }).then((record) => {
    invalidateAgentScope(agentId);
    return record;
  });
}

export function restoreAgent(agentId: string) {
  return requestJson<AgentLifecycleRecord>(`/api/v1/platform/agents/${agentId}/restore`, {
    method: "POST",
  }).then((record) => {
    invalidateAgentScope(agentId);
    return record;
  });
}

export function purgeAgent(agentId: string) {
  return requestJson<{ ok: boolean; id: string; kind: string }>(`/api/v1/platform/agents/${agentId}/purge`, {
    method: "DELETE",
  }).then((record) => {
    invalidateAgentScope(agentId);
    return record;
  });
}

export function getAgentDetails(agentId: string) {
  return requestJson<AgentDetails>(`/api/v1/agents/${agentId}/details`, { cacheTtlMs: 20_000 });
}

export function getPersistentState(agentId: string, limit = 120) {
  return requestJson<PersistentState>(`/api/v1/agents/${agentId}/persistent_state?limit=${limit}`, { cacheTtlMs: 20_000 });
}

export function getRawPrompt(agentId: string) {
  return requestJson<{ messages: Array<{ role: string; content: string }> }>(`/api/v1/agents/${agentId}/raw_prompt`, {
    cacheTtlMs: 20_000,
  });
}

export function sendChat(
  agentId: string,
  message: string,
  options?: {
    timeout_seconds?: number;
    retry_count?: number;
  },
) {
  return requestJson<ChatResult>("/api/v1/chat", {
    method: "POST",
    body: {
      agent_id: agentId,
      message,
      timeout_seconds: options?.timeout_seconds,
      retry_count: options?.retry_count,
    },
  }).then((result) => {
    invalidateAgentScope(agentId);
    return result;
  });
}

export function generateComment(payload: {
  input: string;
  prompt_key: string;
  persona_key: string;
  model_key?: string;
  model?: string;
  max_tokens?: number;
  timeout_seconds?: number;
  retry_count?: number;
  task_shape?: CommentingTaskShape;
  cache_prompt?: boolean;
  temperature?: number;
  top_p?: number;
}) {
  return requestJson<CommentingGenerateResponse>("/api/v1/commenting/generate", {
    method: "POST",
    body: {
      scenario: "comment",
      input: payload.input,
      prompt_key: payload.prompt_key,
      persona_key: payload.persona_key,
      model_key: payload.model_key?.trim() || undefined,
      model: payload.model?.trim() || undefined,
      max_tokens: payload.max_tokens,
      timeout_seconds: payload.timeout_seconds,
      retry_count: payload.retry_count,
      task_shape: payload.task_shape,
      cache_prompt: payload.cache_prompt,
      temperature: payload.temperature,
      top_p: payload.top_p,
    },
  });
}

export function generateLabels(payload: {
  input: string;
  prompt_key: string;
  schema_key: string;
  model_key: string;
  max_tokens?: number;
  timeout_seconds?: number;
  repair_retry_count?: number;
  temperature?: number;
  top_p?: number;
}) {
  return requestJson<LabelingGenerateResponse>("/api/v1/labeling/generate", {
    method: "POST",
    body: {
      scenario: "label",
      input: payload.input,
      prompt_key: payload.prompt_key,
      schema_key: payload.schema_key,
      model_key: payload.model_key.trim(),
      max_tokens: payload.max_tokens,
      timeout_seconds: payload.timeout_seconds,
      repair_retry_count: payload.repair_retry_count,
      temperature: payload.temperature,
      top_p: payload.top_p,
    },
  });
}

export function listLabelSchemas(includeArchived = false) {
  const params = new URLSearchParams();
  params.set("include_archived", includeArchived ? "true" : "false");
  return requestJson<{
    total: number;
    include_archived: boolean;
    items: LabelSchemaRecord[];
  }>(`/api/v1/platform/schema-center/label-schemas?${params.toString()}`, { cacheTtlMs: 10_000 });
}

export function createLabelSchema(payload: {
  key: string;
  label?: string;
  description?: string;
  schema: Record<string, unknown>;
}) {
  return requestJson<LabelSchemaRecord>("/api/v1/platform/schema-center/label-schemas", {
    method: "POST",
    body: payload,
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/schema-center", "/api/v1/options"]);
    return record;
  });
}

export function updateLabelSchema(
  key: string,
  payload: {
    label?: string;
    description?: string;
    schema?: Record<string, unknown>;
  },
) {
  return requestJson<LabelSchemaRecord>(`/api/v1/platform/schema-center/label-schemas/${key}`, {
    method: "PATCH",
    body: payload,
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/schema-center", "/api/v1/options"]);
    return record;
  });
}

export function archiveLabelSchema(key: string) {
  return requestJson<LabelSchemaRecord>(`/api/v1/platform/schema-center/label-schemas/${key}/archive`, {
    method: "POST",
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/schema-center", "/api/v1/options"]);
    return record;
  });
}

export function restoreLabelSchema(key: string) {
  return requestJson<LabelSchemaRecord>(`/api/v1/platform/schema-center/label-schemas/${key}/restore`, {
    method: "POST",
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/schema-center", "/api/v1/options"]);
    return record;
  });
}

export function purgeLabelSchema(key: string) {
  return requestJson<{ ok: boolean; key: string; kind: string }>(`/api/v1/platform/schema-center/label-schemas/${key}/purge`, {
    method: "DELETE",
  }).then((result) => {
    invalidateApiCache(["/api/v1/platform/schema-center", "/api/v1/options"]);
    return result;
  });
}

export function fetchPromptPersonaMetadata(scenario: Scenario = "chat") {
  const params = new URLSearchParams();
  params.set("scenario", scenario);
  return requestJson<{
    defaults: {
      scenario: Scenario;
      prompt_key: string;
      persona_key: string;
    };
    prompts: Array<{
      scenario: Scenario;
      key: string;
      label: string;
      description: string;
      preview: string;
      length: number;
    }>;
    personas: Array<{
      scenario: Scenario;
      key: string;
      preview: string;
      length: number;
    }>;
  }>(`/api/v1/platform/metadata/prompts-personas?${params.toString()}`, { cacheTtlMs: 60_000 });
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
  }>(`/api/v1/platform/metadata/prompts-personas/revisions?${params.toString()}`, { cacheTtlMs: 10_000 });
}

export function updateSystemPrompt(agentId: string, system: string) {
  return requestJson<{ system_after: string; system_before: string }>(`/api/v1/platform/agents/${agentId}/system`, {
    method: "PATCH",
    body: { system },
  }).then((payload) => {
    invalidateAgentScope(agentId);
    return payload;
  });
}

export function updateAgentModel(agentId: string, model: string) {
  return requestJson<{ model_after: string; model_before: string }>(`/api/v1/platform/agents/${agentId}/model`, {
    method: "PATCH",
    body: { model },
  }).then((payload) => {
    invalidateAgentScope(agentId);
    return payload;
  });
}

export function updateCoreMemoryBlock(agentId: string, blockLabel: string, value: string) {
  return requestJson<{ value_before: string; value_after: string }>(
    `/api/v1/platform/agents/${agentId}/core-memory/blocks/${blockLabel}`,
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
  }>(`/api/v1/platform/tools?${params.toString()}`, { cacheTtlMs: 20_000 });
}

export function testInvokeTool(payload: {
  agent_id: string;
  input: string;
  expected_tool_name?: string;
  override_model?: string;
  override_system?: string;
  timeout_seconds?: number;
  retry_count?: number;
}) {
  return requestJson<PlatformToolTestInvokeResult>("/api/v1/platform/tools/test-invoke", {
    method: "POST",
    body: payload,
  }).then((result) => {
    invalidateAgentScope(payload.agent_id || "");
    return result;
  });
}

export function attachTool(agentId: string, toolId: string) {
  return requestJson(`/api/v1/platform/agents/${agentId}/tools/attach/${toolId}`, {
    method: "PATCH",
  }).then((payload) => {
    invalidateAgentScope(agentId);
    return payload;
  });
}

export function detachTool(agentId: string, toolId: string) {
  return requestJson(`/api/v1/platform/agents/${agentId}/tools/detach/${toolId}`, {
    method: "PATCH",
  }).then((payload) => {
    invalidateAgentScope(agentId);
    return payload;
  });
}

export function listPromptTemplates(includeArchived = false, scenario?: Scenario) {
  const params = new URLSearchParams();
  params.set("include_archived", includeArchived ? "true" : "false");
  if (scenario) {
    params.set("scenario", scenario);
  }
  return requestJson<{
    total: number;
    scenario?: Scenario | null;
    include_archived: boolean;
    items: PromptTemplateRecord[];
  }>(`/api/v1/platform/prompt-center/prompts?${params.toString()}`, { cacheTtlMs: 10_000 });
}

export function createPromptTemplate(payload: {
  scenario?: Scenario;
  key: string;
  label?: string;
  description?: string;
  content: string;
}) {
  return requestJson<PromptTemplateRecord>("/api/v1/platform/prompt-center/prompts", {
    method: "POST",
    body: payload,
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/prompt-center", "/api/v1/options", "/api/v1/platform/metadata/prompts-personas"]);
    return record;
  });
}

export function updatePromptTemplate(
  key: string,
  payload: {
    label?: string;
    description?: string;
    content?: string;
  },
  scenario?: Scenario,
) {
  const params = new URLSearchParams();
  if (scenario) {
    params.set("scenario", scenario);
  }
  const query = params.toString();
  return requestJson<PromptTemplateRecord>(`/api/v1/platform/prompt-center/prompts/${key}${query ? `?${query}` : ""}`, {
    method: "PATCH",
    body: payload,
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/prompt-center", "/api/v1/options", "/api/v1/platform/metadata/prompts-personas"]);
    return record;
  });
}

export function archivePromptTemplate(key: string, scenario?: Scenario) {
  const params = new URLSearchParams();
  if (scenario) {
    params.set("scenario", scenario);
  }
  return requestJson<PromptTemplateRecord>(`/api/v1/platform/prompt-center/prompts/${key}/archive?${params.toString()}`, {
    method: "POST",
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/prompt-center", "/api/v1/options", "/api/v1/platform/metadata/prompts-personas"]);
    return record;
  });
}

export function restorePromptTemplate(key: string, scenario?: Scenario) {
  const params = new URLSearchParams();
  if (scenario) {
    params.set("scenario", scenario);
  }
  return requestJson<PromptTemplateRecord>(`/api/v1/platform/prompt-center/prompts/${key}/restore?${params.toString()}`, {
    method: "POST",
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/prompt-center", "/api/v1/options", "/api/v1/platform/metadata/prompts-personas"]);
    return record;
  });
}

export function purgePromptTemplate(key: string, scenario?: Scenario) {
  const params = new URLSearchParams();
  if (scenario) {
    params.set("scenario", scenario);
  }
  return requestJson<{ ok: boolean; key: string; kind: string }>(`/api/v1/platform/prompt-center/prompts/${key}/purge?${params.toString()}`, {
    method: "DELETE",
  }).then((result) => {
    invalidateApiCache(["/api/v1/platform/prompt-center", "/api/v1/options", "/api/v1/platform/metadata/prompts-personas"]);
    return result;
  });
}

export function listPersonaTemplates(includeArchived = false, scenario?: Scenario) {
  const params = new URLSearchParams();
  params.set("include_archived", includeArchived ? "true" : "false");
  if (scenario) {
    params.set("scenario", scenario);
  }
  return requestJson<{
    total: number;
    scenario?: Scenario | null;
    include_archived: boolean;
    items: PromptTemplateRecord[];
  }>(`/api/v1/platform/prompt-center/personas?${params.toString()}`, { cacheTtlMs: 10_000 });
}

export function createPersonaTemplate(payload: {
  scenario?: Scenario;
  key: string;
  label?: string;
  description?: string;
  content: string;
}) {
  return requestJson<PromptTemplateRecord>("/api/v1/platform/prompt-center/personas", {
    method: "POST",
    body: payload,
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/prompt-center", "/api/v1/options", "/api/v1/platform/metadata/prompts-personas"]);
    return record;
  });
}

export function updatePersonaTemplate(
  key: string,
  payload: {
    label?: string;
    description?: string;
    content?: string;
  },
  scenario?: Scenario,
) {
  const params = new URLSearchParams();
  if (scenario) {
    params.set("scenario", scenario);
  }
  const query = params.toString();
  return requestJson<PromptTemplateRecord>(`/api/v1/platform/prompt-center/personas/${key}${query ? `?${query}` : ""}`, {
    method: "PATCH",
    body: payload,
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/prompt-center", "/api/v1/options", "/api/v1/platform/metadata/prompts-personas"]);
    return record;
  });
}

export function archivePersonaTemplate(key: string, scenario?: Scenario) {
  const params = new URLSearchParams();
  if (scenario) {
    params.set("scenario", scenario);
  }
  return requestJson<PromptTemplateRecord>(`/api/v1/platform/prompt-center/personas/${key}/archive?${params.toString()}`, {
    method: "POST",
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/prompt-center", "/api/v1/options", "/api/v1/platform/metadata/prompts-personas"]);
    return record;
  });
}

export function restorePersonaTemplate(key: string, scenario?: Scenario) {
  const params = new URLSearchParams();
  if (scenario) {
    params.set("scenario", scenario);
  }
  return requestJson<PromptTemplateRecord>(`/api/v1/platform/prompt-center/personas/${key}/restore?${params.toString()}`, {
    method: "POST",
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/prompt-center", "/api/v1/options", "/api/v1/platform/metadata/prompts-personas"]);
    return record;
  });
}

export function purgePersonaTemplate(key: string, scenario?: Scenario) {
  const params = new URLSearchParams();
  if (scenario) {
    params.set("scenario", scenario);
  }
  return requestJson<{ ok: boolean; key: string; kind: string }>(`/api/v1/platform/prompt-center/personas/${key}/purge?${params.toString()}`, {
    method: "DELETE",
  }).then((result) => {
    invalidateApiCache(["/api/v1/platform/prompt-center", "/api/v1/options", "/api/v1/platform/metadata/prompts-personas"]);
    return result;
  });
}

export function listToolCenterTools(options?: {
  includeArchived?: boolean;
  includeBuiltin?: boolean;
  includeSource?: boolean;
  search?: string;
}) {
  const params = new URLSearchParams();
  params.set("include_archived", options?.includeArchived ? "true" : "false");
  params.set("include_builtin", options?.includeBuiltin === false ? "false" : "true");
  params.set("include_source", options?.includeSource ? "true" : "false");
  if (options?.search?.trim()) {
    params.set("search", options.search.trim());
  }

  return requestJson<{
    total: number;
    include_archived: boolean;
    include_builtin: boolean;
    items: ToolCenterItem[];
  }>(`/api/v1/platform/tool-center/tools?${params.toString()}`, { cacheTtlMs: 8_000 });
}

export function getToolCenterTool(slug: string, includeSource = true) {
  const params = new URLSearchParams();
  params.set("include_source", includeSource ? "true" : "false");
  return requestJson<ToolCenterItem>(`/api/v1/platform/tool-center/tools/${slug}?${params.toString()}`, {
    cacheTtlMs: 8_000,
  });
}

export function createToolCenterTool(payload: {
  slug: string;
  source_code: string;
  description?: string;
  tags?: string[];
  source_type?: string;
  enable_parallel_execution?: boolean;
  default_requires_approval?: boolean;
  return_char_limit?: number;
  pip_requirements?: Array<Record<string, unknown>>;
  npm_requirements?: Array<Record<string, unknown>>;
}) {
  return requestJson<ToolCenterItem>("/api/v1/platform/tool-center/tools", {
    method: "POST",
    body: payload,
  }).then((item) => {
    invalidateApiCache(["/api/v1/platform/tool-center", "/api/v1/platform/tools"]);
    return item;
  });
}

export function updateToolCenterTool(
  slug: string,
  payload: {
    source_code?: string;
    description?: string;
    tags?: string[];
    source_type?: string;
    enable_parallel_execution?: boolean;
    default_requires_approval?: boolean;
    return_char_limit?: number;
    pip_requirements?: Array<Record<string, unknown>>;
    npm_requirements?: Array<Record<string, unknown>>;
  },
) {
  return requestJson<ToolCenterItem>(`/api/v1/platform/tool-center/tools/${slug}`, {
    method: "PATCH",
    body: payload,
  }).then((item) => {
    invalidateApiCache(["/api/v1/platform/tool-center", "/api/v1/platform/tools"]);
    return item;
  });
}

export function archiveToolCenterTool(slug: string) {
  return requestJson<ToolCenterItem>(`/api/v1/platform/tool-center/tools/${slug}/archive`, {
    method: "POST",
  }).then((item) => {
    invalidateApiCache(["/api/v1/platform/tool-center", "/api/v1/platform/tools"]);
    return item;
  });
}

export function restoreToolCenterTool(slug: string) {
  return requestJson<ToolCenterItem>(`/api/v1/platform/tool-center/tools/${slug}/restore`, {
    method: "POST",
  }).then((item) => {
    invalidateApiCache(["/api/v1/platform/tool-center", "/api/v1/platform/tools"]);
    return item;
  });
}

export function purgeToolCenterTool(slug: string) {
  return requestJson<{ ok: boolean; slug: string; kind: string }>(`/api/v1/platform/tool-center/tools/${slug}/purge`, {
    method: "DELETE",
  }).then((result) => {
    invalidateApiCache(["/api/v1/platform/tool-center", "/api/v1/platform/tools"]);
    return result;
  });
}

export function listTestRuns() {
  return requestJson<{ items: PlatformRunRecord[] }>("/api/v1/platform/test-runs", { cacheTtlMs: 3_000 });
}

export function createTestRun(payload: {
  run_type: PlatformRunType;
}) {
  return requestJson<PlatformRunRecord>("/api/v1/platform/test-runs", {
    method: "POST",
    body: payload,
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/test-runs"]);
    return record;
  });
}

export function getTestRun(runId: string) {
  return requestJson<PlatformRunRecord>(`/api/v1/platform/test-runs/${runId}`, { cacheTtlMs: 3_000 });
}

export function cancelTestRun(runId: string) {
  return requestJson<PlatformRunRecord>(`/api/v1/platform/test-runs/${runId}/cancel`, {
    method: "POST",
  }).then((record) => {
    invalidateApiCache(["/api/v1/platform/test-runs"]);
    return record;
  });
}

export function listRunArtifacts(runId: string) {
  return requestJson<{
    run_id: string;
    items: PlatformArtifact[];
  }>(`/api/v1/platform/test-runs/${runId}/artifacts`, { cacheTtlMs: 5_000 });
}

export function readRunArtifact(runId: string, artifactId: string, maxLines = 400) {
  return requestJson<{
    run_id: string;
    artifact: PlatformArtifact;
    content: string;
    truncated: boolean;
    line_count: number;
  }>(`/api/v1/platform/test-runs/${runId}/artifacts/${artifactId}?max_lines=${maxLines}`, { cacheTtlMs: 5_000 });
}

