"use client";

import { useEffect, useState } from "react";

import { CommentingTaskShape, OptionEntry, fetchOptions, generateComment } from "../../lib/api";
import { useI18n } from "../../lib/i18n";

const COPY = {
  en: {
    kicker: "Stateless Module",
    title: "Comment Lab",
    intro:
      "Generate one-shot comments with independent prompt/persona/model controls. This route stays stateless and supports three explicit task-shape strategies.",
    tuningTitle: "Tuning Settings",
    mainContentTitle: "Content Workspace",
    innerWorksTitle: "Inner Works",
    defaultsFromEnv: "Defaults are loaded from runtime environment and can be overridden per request.",
    model: "Model",
    selectModel: "Select model",
    prompt: "Prompt",
    persona: "Persona",
    maxTokens: "Max Tokens",
    maxTokensHint: "Set 0 for no max token limit.",
    timeoutSeconds: "Timeout (seconds)",
    retryCount: "Retry Count",
    retryCountHint: "Set 0 to disable retries. Maximum 5.",
    taskShape: "Task Shape",
    taskShapeClassic: "Classic (persona in user)",
    taskShapeAllInSystem: "All in system",
    taskShapeStructuredOutput: "Structured output (JSON)",
    cachePrompt: "Use prompt cache",
    cachePromptHint: "Off by default for fair persona comparisons on llama-server.",
    temperature: "Temperature",
    topP: "Top P",
    userInput: "Input Text",
    userInputPlaceholder: "Paste a news summary, a thread excerpt, or your own draft context here...",
    generate: "Generate Comment",
    generating: "Generating...",
    refreshOptions: "Refresh Options",
    optionsRefreshed: "Commenting options refreshed.",
    outputTitle: "Generated Comment",
    outputPlaceholder: "Generated content will appear here.",
    provider: "Provider",
    modelUsed: "Model Used",
    maxTokensUsed: "Max Tokens Used",
    timeoutUsed: "Timeout Used",
    taskShapeUsed: "Task Shape Used",
    cachePromptUsed: "Prompt Cache Used",
    temperatureUsed: "Temperature Used",
    topPUsed: "Top P Used",
    runtimeMetaTitle: "Runtime",
    timingMetaTitle: "Timing",
    tokenMetaTitle: "Token Usage",
    responseSeconds: "Response Time (s)",
    usagePromptTokens: "Prompt Tokens",
    usageCompletionTokens: "Completion Tokens",
    usageTotalTokens: "Total Tokens",
    usageReasoningTokens: "Reasoning Tokens",
    receivedAt: "Response Received At",
    selectedAttempt: "Selected Attempt",
    finishReason: "Finish Reason",
    rawRequestTitle: "Raw Request",
    rawRequestPlaceholder: "Raw provider request JSON will appear here.",
    rawReplyTitle: "Raw Model Reply",
    rawReplyPlaceholder: "Raw provider response JSON will appear here.",
    popOutCard: "Pop Out Card",
    closeCard: "Close",
    readableView: "Readable View",
    rawJsonView: "Raw JSON",
    notesTitle: "Execution Notes",
    notesOne: "This route is stateless and does not create or modify Letta agent state.",
    notesTwo: "No embedding model is required for this commenting flow.",
    notesThree: "Provider requests are sent through an OpenAI-compatible chat completions endpoint.",
    notesFour: "Structured output shape requests JSON and extracts the comment field.",
    selectRequired: "Please choose model, prompt, and persona before generating.",
    inputRequired: "Input text is required.",
    invalidMaxTokens: "Max tokens must be a non-negative integer (0 means no limit).",
    invalidTimeout: "Timeout must be a positive number.",
    invalidRetryCount: "Retry count must be an integer between 0 and 5.",
    invalidTemperature: "Temperature must be between 0 and 2.",
    invalidTopP: "Top P must be greater than 0 and at most 1.",
    loadingError: "Failed to load commenting options",
    generateError: "Comment generation failed",
  },
  zh: {
    kicker: "无状态模块",
    title: "评论实验室",
    intro: "以独立模型、Prompt、Persona 控制进行单次评论生成。该页面保持无状态，并支持三种明确的任务形状策略。",
    tuningTitle: "参数调优",
    mainContentTitle: "内容工作区",
    innerWorksTitle: "内部信息",
    defaultsFromEnv: "默认值来自运行环境，可在每次请求中覆盖。",
    model: "模型",
    selectModel: "选择模型",
    prompt: "Prompt",
    persona: "Persona",
    maxTokens: "最大 Token",
    maxTokensHint: "设置为 0 表示不限制最大 Token。",
    timeoutSeconds: "超时时间（秒）",
    retryCount: "重试次数",
    retryCountHint: "设置为 0 表示禁用重试，最大为 5。",
    taskShape: "任务形状",
    taskShapeClassic: "经典模式（persona 放在 user）",
    taskShapeAllInSystem: "全部放在 system",
    taskShapeStructuredOutput: "结构化输出（JSON）",
    cachePrompt: "使用 Prompt 缓存",
    cachePromptHint: "默认关闭，便于在 llama-server 上公平比较 Persona。",
    temperature: "Temperature",
    topP: "Top P",
    userInput: "输入文本",
    userInputPlaceholder: "粘贴新闻摘要、评论串内容，或你的草稿上下文...",
    generate: "生成评论",
    generating: "生成中...",
    refreshOptions: "刷新配置",
    optionsRefreshed: "评论配置已刷新。",
    outputTitle: "生成结果",
    outputPlaceholder: "生成内容会显示在这里。",
    provider: "Provider",
    modelUsed: "使用模型",
    maxTokensUsed: "实际最大 Token",
    timeoutUsed: "实际超时",
    taskShapeUsed: "实际任务形状",
    cachePromptUsed: "实际 Prompt 缓存",
    temperatureUsed: "实际 Temperature",
    topPUsed: "实际 Top P",
    runtimeMetaTitle: "运行参数",
    timingMetaTitle: "时序",
    tokenMetaTitle: "Token 使用",
    responseSeconds: "响应耗时（秒）",
    usagePromptTokens: "输入 Token",
    usageCompletionTokens: "输出 Token",
    usageTotalTokens: "总 Token",
    usageReasoningTokens: "推理 Token",
    receivedAt: "响应接收时间",
    selectedAttempt: "命中尝试",
    finishReason: "完成原因",
    rawRequestTitle: "原始请求",
    rawRequestPlaceholder: "这里会显示发送给 provider 的原始请求 JSON。",
    rawReplyTitle: "模型原始回复",
    rawReplyPlaceholder: "这里会显示 provider 返回的原始 JSON。",
    popOutCard: "弹出卡片",
    closeCard: "关闭",
    readableView: "可读视图",
    rawJsonView: "原始 JSON",
    notesTitle: "执行说明",
    notesOne: "该路径为无状态，不会创建或修改 Letta 智能体状态。",
    notesTwo: "该评论流程不需要 embedding 模型。",
    notesThree: "请求通过 OpenAI 兼容的 chat completions 接口发送。",
    notesFour: "结构化输出模式会请求 JSON，并提取其中的 comment 字段。",
    selectRequired: "生成前请先选择模型、Prompt 与 Persona。",
    inputRequired: "请输入文本。",
    invalidMaxTokens: "最大 Token 必须是非负整数（0 表示不限制）。",
    invalidTimeout: "超时时间必须是正数。",
    invalidRetryCount: "重试次数必须是 0 到 5 之间的整数。",
    invalidTemperature: "Temperature 必须在 0 到 2 之间。",
    invalidTopP: "Top P 必须大于 0 且不超过 1。",
    loadingError: "加载评论配置失败",
    generateError: "评论生成失败",
  },
} as const;

function toErrorMessage(exc: unknown): string {
  return exc instanceof Error ? exc.message : String(exc);
}

function optionLabel(option: OptionEntry): string {
  const key = (option.provider_model_id || option.key || "").trim();
  const label = (option.label || "").trim();
  const sourceLabel = (option.source_label || "").trim();
  const base = label && label !== key ? `${label} (${key})` : key;
  if (sourceLabel) {
    return `${base} - ${sourceLabel}`;
  }
  return base;
}

function pickSelectedKey(current: string, options: OptionEntry[], fallback: string): string {
  if (current && options.some((option) => option.key === current)) {
    return current;
  }
  const preferred = options.find((option) => option.is_default)?.key || "";
  return preferred || options[0]?.key || fallback;
}

function parseNonNegativeInt(value: string): number | null {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }
  return parsed;
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

function parseTemperature(value: string): number | null {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 2) {
    return null;
  }
  return parsed;
}

function parseTopP(value: string): number | null {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 1) {
    return null;
  }
  return parsed;
}

function asObject(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function asIntString(value: unknown): string {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) {
    return "";
  }
  return String(parsed);
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function stringifyPretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function normalizeChatContent(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        const obj = asObject(item);
        const text = typeof obj.text === "string" ? obj.text : "";
        return text.trim();
      })
      .filter((part) => part.length > 0)
      .join("\n")
      .trim();
  }
  if (value === undefined || value === null) {
    return "";
  }
  return String(value).trim();
}

function formatRawRequestForHuman(value: unknown): string {
  const payload = asObject(value);
  if (!Object.keys(payload).length) {
    return "-";
  }

  const lines: string[] = [];
  lines.push(`Model: ${String(payload.model ?? "-")}`);
  lines.push(`Temperature: ${String(payload.temperature ?? "-")}`);
  lines.push(`Top P: ${String(payload.top_p ?? "-")}`);
  lines.push(`Cache Prompt: ${String(payload.cache_prompt ?? "-")}`);
  lines.push(`Max Tokens: ${String(payload.max_tokens ?? "-")}`);

  const messages = Array.isArray(payload.messages) ? payload.messages : [];
  lines.push(`Message Count: ${messages.length}`);

  messages.forEach((message, index) => {
    const obj = asObject(message);
    const role = String(obj.role ?? "unknown");
    const content = normalizeChatContent(obj.content);
    lines.push("");
    lines.push(`Message ${index + 1} (${role})`);
    lines.push(content || "-");
  });

  return lines.join("\n").trim();
}

function formatRawReplyForHuman(value: unknown): string {
  const payload = asObject(value);
  if (!Object.keys(payload).length) {
    return "-";
  }

  const lines: string[] = [];
  lines.push(`ID: ${String(payload.id ?? "-")}`);
  lines.push(`Model: ${String(payload.model ?? "-")}`);

  const usage = asObject(payload.usage);
  if (Object.keys(usage).length) {
    lines.push(
      `Usage: prompt=${String(usage.prompt_tokens ?? "-")}, completion=${String(usage.completion_tokens ?? "-")}, total=${String(usage.total_tokens ?? "-")}`,
    );
  }

  const choices = Array.isArray(payload.choices) ? payload.choices : [];
  lines.push(`Choices: ${choices.length}`);

  choices.forEach((choice, index) => {
    const choiceObj = asObject(choice);
    const finishReason = String(choiceObj.finish_reason ?? "-");
    const message = asObject(choiceObj.message);
    const content = normalizeChatContent(message.content);
    const reasoning = normalizeChatContent(message.reasoning_content);

    lines.push("");
    lines.push(`Choice ${index + 1}`);
    lines.push(`Finish Reason: ${finishReason}`);
    lines.push("Assistant Content:");
    lines.push(content || "-");
    if (reasoning) {
      lines.push("");
      lines.push("Reasoning Content:");
      lines.push(reasoning);
    }
  });

  return lines.join("\n").trim();
}

function previewText(value: string, maxChars = 760): string {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  if (text.length <= maxChars) {
    return text;
  }
  return `${text.slice(0, maxChars)}\n\n...`;
}

export default function CommentLabPage() {
  const { locale } = useI18n();
  const copy = COPY[locale];

  const [loadingOptions, setLoadingOptions] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const [models, setModels] = useState<OptionEntry[]>([]);
  const [prompts, setPrompts] = useState<OptionEntry[]>([]);
  const [personas, setPersonas] = useState<OptionEntry[]>([]);

  const [model, setModel] = useState("");
  const [promptKey, setPromptKey] = useState("");
  const [personaKey, setPersonaKey] = useState("");
  const [maxTokens, setMaxTokens] = useState("0");
  const [timeoutSeconds, setTimeoutSeconds] = useState("180");
  const [retryCount, setRetryCount] = useState("0");
  const [taskShape, setTaskShape] = useState<CommentingTaskShape>("classic");
  const [cachePrompt, setCachePrompt] = useState(false);
  const [temperature, setTemperature] = useState("0.6");
  const [topP, setTopP] = useState("1");

  const [userInput, setUserInput] = useState("");
  const [output, setOutput] = useState("");
  const [provider, setProvider] = useState("");
  const [modelUsed, setModelUsed] = useState("");
  const [maxTokensUsed, setMaxTokensUsed] = useState("");
  const [timeoutUsed, setTimeoutUsed] = useState("");
  const [taskShapeUsed, setTaskShapeUsed] = useState("");
  const [cachePromptUsed, setCachePromptUsed] = useState("");
  const [temperatureUsed, setTemperatureUsed] = useState("");
  const [topPUsed, setTopPUsed] = useState("");
  const [usagePromptTokens, setUsagePromptTokens] = useState("");
  const [usageCompletionTokens, setUsageCompletionTokens] = useState("");
  const [usageTotalTokens, setUsageTotalTokens] = useState("");
  const [usageReasoningTokens, setUsageReasoningTokens] = useState("");
  const [responseSeconds, setResponseSeconds] = useState("");
  const [receivedAt, setReceivedAt] = useState("");
  const [selectedAttempt, setSelectedAttempt] = useState("");
  const [finishReason, setFinishReason] = useState("");
  const [rawRequest, setRawRequest] = useState("");
  const [rawRequestReadable, setRawRequestReadable] = useState("");
  const [rawReply, setRawReply] = useState("");
  const [rawReplyReadable, setRawReplyReadable] = useState("");
  const [popOutCard, setPopOutCard] = useState<{ title: string; readable: string; raw: string } | null>(null);

  const loadOptions = async (forceRefresh = false) => {
    setLoadingOptions(true);
    setError("");

    try {
      const payload = await fetchOptions("comment", forceRefresh ? { refresh: true } : undefined);
      const nextModels = Array.isArray(payload.models) ? payload.models : [];
      const nextPrompts = Array.isArray(payload.prompts) ? payload.prompts : [];
      const nextPersonas = Array.isArray(payload.personas) ? payload.personas : [];

      setModels(nextModels);
      setPrompts(nextPrompts);
      setPersonas(nextPersonas);

      setModel((current) => (current && nextModels.some((option) => option.key === current) ? current : ""));
      const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
      const requestedPromptKey = (params?.get("promptKey") || "").trim();
      const requestedPersonaKey = (params?.get("personaKey") || "").trim();

      setPromptKey((current) => {
        if (current && nextPrompts.some((option) => option.key === current)) {
          return current;
        }
        if (requestedPromptKey && nextPrompts.some((option) => option.key === requestedPromptKey)) {
          return requestedPromptKey;
        }
        return pickSelectedKey("", nextPrompts, payload.defaults.prompt_key || "");
      });
      setPersonaKey((current) => {
        if (current && nextPersonas.some((option) => option.key === current)) {
          return current;
        }
        if (requestedPersonaKey && nextPersonas.some((option) => option.key === requestedPersonaKey)) {
          return requestedPersonaKey;
        }
        return pickSelectedKey("", nextPersonas, payload.defaults.persona_key || "");
      });
      if (payload.commenting) {
        setMaxTokens(`${payload.commenting.max_tokens}`);
        setTimeoutSeconds(`${payload.commenting.timeout_seconds}`);
        setTaskShape(payload.commenting.task_shape);
        setCachePrompt(Boolean(payload.commenting.cache_prompt));
        setTemperature(`${payload.commenting.temperature}`);
        setTopP(`${payload.commenting.top_p}`);
      }

      setStatus(copy.optionsRefreshed);
    } catch (exc) {
      setError(`${copy.loadingError}: ${toErrorMessage(exc)}`);
    } finally {
      setLoadingOptions(false);
    }
  };

  useEffect(() => {
    void loadOptions();
  }, []);

  const onGenerate = async () => {
    setError("");
    setStatus("");
    setPopOutCard(null);
    setResponseSeconds("");

    if (!model || !promptKey || !personaKey) {
      setError(copy.selectRequired);
      return;
    }

    if (!userInput.trim()) {
      setError(copy.inputRequired);
      return;
    }

    const parsedMaxTokens = parseNonNegativeInt(maxTokens);
    if (parsedMaxTokens === null) {
      setError(copy.invalidMaxTokens);
      return;
    }

    const parsedTimeoutSeconds = parsePositiveFloat(timeoutSeconds);
    if (parsedTimeoutSeconds === null) {
      setError(copy.invalidTimeout);
      return;
    }
    const parsedRetryCount = parseRetryCount(retryCount);
    if (parsedRetryCount === null) {
      setError(copy.invalidRetryCount);
      return;
    }
    const parsedTemperature = parseTemperature(temperature);
    if (parsedTemperature === null) {
      setError(copy.invalidTemperature);
      return;
    }
    const parsedTopP = parseTopP(topP);
    if (parsedTopP === null) {
      setError(copy.invalidTopP);
      return;
    }

    setSubmitting(true);
    const startedAtMs = performance.now();
    try {
      const payload = await generateComment({
        input: userInput,
        prompt_key: promptKey,
        persona_key: personaKey,
        model_key: model,
        max_tokens: parsedMaxTokens,
        timeout_seconds: parsedTimeoutSeconds,
        retry_count: parsedRetryCount,
        task_shape: taskShape,
        cache_prompt: cachePrompt,
        temperature: parsedTemperature,
        top_p: parsedTopP,
      });
      setOutput(payload.content || "");
      setProvider(payload.provider || "");
      setModelUsed(payload.provider_model_id || payload.model || "");
      setMaxTokensUsed(`${payload.max_tokens}`);
      setTimeoutUsed(`${payload.timeout_seconds}`);
      setTaskShapeUsed(payload.task_shape || "");
      setCachePromptUsed(payload.cache_prompt ? "true" : "false");
      setTemperatureUsed(`${payload.temperature}`);
      setTopPUsed(`${payload.top_p}`);
      const usage = asObject(payload.usage);
      const completionTokensDetails = asObject(usage.completion_tokens_details);
      setUsagePromptTokens(asIntString(usage.prompt_tokens));
      setUsageCompletionTokens(asIntString(usage.completion_tokens));
      setUsageTotalTokens(asIntString(usage.total_tokens));
      setUsageReasoningTokens(asIntString(completionTokensDetails.reasoning_tokens));
      setResponseSeconds((Math.max(0, performance.now() - startedAtMs) / 1000).toFixed(2));
      setReceivedAt(payload.received_at || "");
      setSelectedAttempt(payload.selected_attempt || "");
      setFinishReason(payload.finish_reason || "");
      setRawRequest(stringifyPretty(payload.raw_request || {}));
      setRawRequestReadable(formatRawRequestForHuman(payload.raw_request || {}));
      setRawReply(stringifyPretty(payload.raw_reply || {}));
      setRawReplyReadable(formatRawReplyForHuman(payload.raw_reply || {}));
      setStatus(`${copy.modelUsed}: ${payload.provider_model_id || payload.model}`);
    } catch (exc) {
      setResponseSeconds("");
      setError(`${copy.generateError}: ${toErrorMessage(exc)}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section>
      <div className="kicker">{copy.kicker}</div>
      <h1 className="section-title">{copy.title}</h1>
      <p className="muted" style={{ maxWidth: 860 }}>
        {copy.intro}
      </p>

      {status ? (
        <div className="card" style={{ marginTop: 12, borderColor: "#86efac" }}>
          <p>{status}</p>
        </div>
      ) : null}

      {error ? (
        <div className="card" style={{ marginTop: 12, borderColor: "#fecaca" }}>
          <p>{error}</p>
        </div>
      ) : null}

      <div className="studio-layout" style={{ marginTop: 14 }}>
        <div className="card studio-panel">
          <h3>{copy.tuningTitle}</h3>
          <div className="form-grid" style={{ marginTop: 10 }}>
            <label className="field">
              <span>{copy.model}</span>
              <select
                className="input"
                value={model}
                onChange={(event) => setModel(event.target.value)}
                disabled={loadingOptions || submitting}
              >
                <option value="">{copy.selectModel}</option>
                {models.map((item) => (
                  <option key={item.key} value={item.key}>
                    {optionLabel(item)}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>{copy.prompt}</span>
              <select
                className="input"
                value={promptKey}
                onChange={(event) => setPromptKey(event.target.value)}
                disabled={loadingOptions || submitting}
              >
                {prompts.map((item) => (
                  <option key={item.key} value={item.key}>
                    {optionLabel(item)}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>{copy.persona}</span>
              <select
                className="input"
                value={personaKey}
                onChange={(event) => setPersonaKey(event.target.value)}
                disabled={loadingOptions || submitting}
              >
                {personas.map((item) => (
                  <option key={item.key} value={item.key}>
                    {optionLabel(item)}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>{copy.maxTokens}</span>
              <input
                className="input"
                type="number"
                min={0}
                max={8192}
                step={1}
                value={maxTokens}
                onChange={(event) => setMaxTokens(event.target.value)}
                disabled={submitting}
              />
              <span className="muted" style={{ fontSize: 12 }}>
                {copy.maxTokensHint}
              </span>
            </label>

            <label className="field">
              <span>{copy.timeoutSeconds}</span>
              <input
                className="input"
                type="number"
                min={5}
                max={600}
                step={1}
                value={timeoutSeconds}
                onChange={(event) => setTimeoutSeconds(event.target.value)}
                disabled={submitting}
              />
            </label>

            <label className="field">
              <span>{copy.retryCount}</span>
              <input
                className="input"
                type="number"
                min={0}
                max={5}
                step={1}
                value={retryCount}
                onChange={(event) => setRetryCount(event.target.value)}
                disabled={submitting}
              />
              <span className="muted" style={{ fontSize: 12 }}>
                {copy.retryCountHint}
              </span>
            </label>

            <label className="field">
              <span>{copy.taskShape}</span>
              <select
                className="input"
                value={taskShape}
                onChange={(event) => setTaskShape(event.target.value as CommentingTaskShape)}
                disabled={submitting}
              >
                <option value="classic">{copy.taskShapeClassic}</option>
                <option value="all_in_system">{copy.taskShapeAllInSystem}</option>
                <option value="structured_output">{copy.taskShapeStructuredOutput}</option>
              </select>
            </label>

            <label className="field">
              <span>{copy.temperature}</span>
              <input
                className="input"
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={temperature}
                onChange={(event) => setTemperature(event.target.value)}
                disabled={submitting}
              />
            </label>

            <label className="field">
              <span>{copy.topP}</span>
              <input
                className="input"
                type="number"
                min={0.01}
                max={1}
                step={0.05}
                value={topP}
                onChange={(event) => setTopP(event.target.value)}
                disabled={submitting}
              />
            </label>

            <label className="field">
              <span>{copy.cachePrompt}</span>
              <label className="muted" style={{ fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={cachePrompt}
                  onChange={(event) => setCachePrompt(event.target.checked)}
                  disabled={submitting}
                  style={{ marginRight: 8 }}
                />
                {copy.cachePromptHint}
              </label>
            </label>
          </div>

          <div className="toolbar" style={{ marginTop: 12 }}>
            <button className="button" onClick={() => void onGenerate()} disabled={loadingOptions || submitting}>
              {submitting ? copy.generating : copy.generate}
            </button>
            <button className="button muted" onClick={() => void loadOptions(true)} disabled={submitting}>
              {copy.refreshOptions}
            </button>
          </div>
          <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
            {copy.defaultsFromEnv}
          </p>
        </div>

        <div className="card studio-panel">
          <h3>{copy.mainContentTitle}</h3>
          <label className="field" style={{ marginTop: 10 }}>
            <span>{copy.userInput}</span>
            <textarea
              className="input"
              rows={12}
              style={{ minHeight: 240 }}
              value={userInput}
              onChange={(event) => setUserInput(event.target.value)}
              placeholder={copy.userInputPlaceholder}
              disabled={submitting}
            />
          </label>

          <hr className="studio-divider" />

          <h3>{copy.outputTitle}</h3>
          <div
            style={{
              marginTop: 10,
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: 10,
            }}
          >
            <div className="card" style={{ margin: 0, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 12, fontWeight: 700 }}>
                {copy.runtimeMetaTitle}
              </div>
              <div className="list" style={{ marginTop: 6 }}>
                <div>
                  {copy.provider}: {provider || "-"}
                </div>
                <div>
                  {copy.modelUsed}: {modelUsed || "-"}
                </div>
                <div>
                  {copy.taskShapeUsed}: {taskShapeUsed || "-"}
                </div>
                <div>
                  {copy.cachePromptUsed}: {cachePromptUsed || "-"}
                </div>
                <div>
                  {copy.temperatureUsed}: {temperatureUsed || "-"}
                </div>
                <div>
                  {copy.topPUsed}: {topPUsed || "-"}
                </div>
                <div>
                  {copy.maxTokensUsed}: {maxTokensUsed || "-"}
                </div>
                <div>
                  {copy.timeoutUsed}: {timeoutUsed || "-"}
                </div>
              </div>
            </div>

            <div className="card" style={{ margin: 0, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 12, fontWeight: 700 }}>
                {copy.timingMetaTitle}
              </div>
              <div className="list" style={{ marginTop: 6 }}>
                <div>
                  {copy.responseSeconds}: {responseSeconds || "-"}
                </div>
                <div>
                  {copy.receivedAt}: {receivedAt ? formatTimestamp(receivedAt) : "-"}
                </div>
              </div>
            </div>

            <div className="card" style={{ margin: 0, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 12, fontWeight: 700 }}>
                {copy.tokenMetaTitle}
              </div>
              <div className="list" style={{ marginTop: 6 }}>
                <div>
                  {copy.usagePromptTokens}: {usagePromptTokens || "-"}
                </div>
                <div>
                  {copy.usageCompletionTokens}: {usageCompletionTokens || "-"}
                </div>
                <div>
                  {copy.usageReasoningTokens}: {usageReasoningTokens || "-"}
                </div>
                <div>
                  {copy.usageTotalTokens}: {usageTotalTokens || "-"}
                </div>
              </div>
            </div>
          </div>
          <div className="code" style={{ marginTop: 10, minHeight: 280 }}>
            {output || copy.outputPlaceholder}
          </div>
        </div>

        <div className="card studio-panel">
          <h3>{copy.innerWorksTitle}</h3>
          <div className="list" style={{ marginTop: 0 }}>
            <div>
              {copy.selectedAttempt}: {selectedAttempt || "-"}
            </div>
            <div>
              {copy.finishReason}: {finishReason || "-"}
            </div>
          </div>

          <div className="toolbar" style={{ marginTop: 14, justifyContent: "space-between" }}>
            <h3 style={{ margin: 0 }}>{copy.rawRequestTitle}</h3>
            <button
              className="button muted"
              onClick={() =>
                setPopOutCard({
                  title: copy.rawRequestTitle,
                  readable: rawRequestReadable,
                  raw: rawRequest,
                })
              }
              disabled={!rawRequest}
            >
              {copy.popOutCard}
            </button>
          </div>
          <div className="code" style={{ marginTop: 10, minHeight: 150, maxHeight: 220, overflowY: "auto" }}>
            {previewText(rawRequestReadable) || copy.rawRequestPlaceholder}
          </div>

          <div className="toolbar" style={{ marginTop: 14, justifyContent: "space-between" }}>
            <h3 style={{ margin: 0 }}>{copy.rawReplyTitle}</h3>
            <button
              className="button muted"
              onClick={() =>
                setPopOutCard({
                  title: copy.rawReplyTitle,
                  readable: rawReplyReadable,
                  raw: rawReply,
                })
              }
              disabled={!rawReply}
            >
              {copy.popOutCard}
            </button>
          </div>
          <div className="code" style={{ marginTop: 10, minHeight: 150, maxHeight: 220, overflowY: "auto" }}>
            {previewText(rawReplyReadable) || copy.rawReplyPlaceholder}
          </div>

          <h3 style={{ marginTop: 14 }}>{copy.notesTitle}</h3>
          <ul className="list">
            <li>{copy.notesOne}</li>
            <li>{copy.notesTwo}</li>
            <li>{copy.notesThree}</li>
            <li>{copy.notesFour}</li>
          </ul>
        </div>
      </div>

      {popOutCard ? (
        <div className="editor-overlay" onClick={() => setPopOutCard(null)}>
          <div
            className="editor-card"
            style={{ width: "min(1100px, 100%)", maxHeight: "88vh", overflowY: "auto" }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="toolbar" style={{ justifyContent: "space-between" }}>
              <h3 style={{ margin: 0 }}>{popOutCard.title}</h3>
              <button className="button muted" onClick={() => setPopOutCard(null)}>
                {copy.closeCard}
              </button>
            </div>

            <h3 style={{ marginTop: 14 }}>{copy.readableView}</h3>
            <div className="code" style={{ marginTop: 10, minHeight: 220, maxHeight: 380, overflowY: "auto" }}>
              {popOutCard.readable || "-"}
            </div>

            <details style={{ marginTop: 14 }}>
              <summary>{copy.rawJsonView}</summary>
              <div className="code" style={{ marginTop: 10, minHeight: 180, maxHeight: 420, overflowY: "auto" }}>
                {popOutCard.raw || "-"}
              </div>
            </details>
          </div>
        </div>
      ) : null}
    </section>
  );
}
