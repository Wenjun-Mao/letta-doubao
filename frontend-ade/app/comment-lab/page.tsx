"use client";

import { useEffect, useState } from "react";

import { OptionEntry, fetchOptions, generateComment } from "../../lib/api";
import { useI18n } from "../../lib/i18n";

const COPY = {
  en: {
    kicker: "Stateless Module",
    title: "Comment Lab",
    intro:
      "Generate one-shot comments with independent prompt/persona/model controls. This route is intentionally separated from Agent Studio chat.",
    model: "Model",
    prompt: "Prompt",
    persona: "Persona",
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
    notesTitle: "Execution Notes",
    notesOne: "This route is stateless and does not create or modify Letta agent state.",
    notesTwo: "No embedding model is required for this commenting flow.",
    notesThree: "Provider requests are sent through an OpenAI-compatible chat completions endpoint.",
    selectRequired: "Please choose model, prompt, and persona before generating.",
    inputRequired: "Input text is required.",
    loadingError: "Failed to load commenting options",
    generateError: "Comment generation failed",
  },
  zh: {
    kicker: "无状态模块",
    title: "评论实验室",
    intro: "以独立模型、Prompt、Persona 控制进行单次评论生成。该页面刻意与 Agent Studio 聊天流程解耦。",
    model: "模型",
    prompt: "Prompt",
    persona: "Persona",
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
    notesTitle: "执行说明",
    notesOne: "该路径为无状态，不会创建或修改 Letta 智能体状态。",
    notesTwo: "该评论流程不需要 embedding 模型。",
    notesThree: "请求通过 OpenAI 兼容的 chat completions 接口发送。",
    selectRequired: "生成前请先选择模型、Prompt 与 Persona。",
    inputRequired: "请输入文本。",
    loadingError: "加载评论配置失败",
    generateError: "评论生成失败",
  },
} as const;

function toErrorMessage(exc: unknown): string {
  return exc instanceof Error ? exc.message : String(exc);
}

function optionLabel(option: OptionEntry): string {
  const label = (option.label || "").trim();
  return label ? `${label} (${option.key})` : option.key;
}

function pickSelectedKey(current: string, options: OptionEntry[], fallback: string): string {
  if (current && options.some((option) => option.key === current)) {
    return current;
  }
  const preferred = options.find((option) => option.is_default)?.key || "";
  return preferred || options[0]?.key || fallback;
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

  const [userInput, setUserInput] = useState("");
  const [output, setOutput] = useState("");
  const [provider, setProvider] = useState("");
  const [modelUsed, setModelUsed] = useState("");

  const loadOptions = async () => {
    setLoadingOptions(true);
    setError("");

    try {
      const payload = await fetchOptions("comment");
      const nextModels = Array.isArray(payload.models) ? payload.models : [];
      const nextPrompts = Array.isArray(payload.prompts) ? payload.prompts : [];
      const nextPersonas = Array.isArray(payload.personas) ? payload.personas : [];

      setModels(nextModels);
      setPrompts(nextPrompts);
      setPersonas(nextPersonas);

      setModel((current) => pickSelectedKey(current, nextModels, payload.defaults.model || ""));
      setPromptKey((current) => pickSelectedKey(current, nextPrompts, payload.defaults.prompt_key || ""));
      setPersonaKey((current) => pickSelectedKey(current, nextPersonas, payload.defaults.persona_key || ""));

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

    if (!model || !promptKey || !personaKey) {
      setError(copy.selectRequired);
      return;
    }

    if (!userInput.trim()) {
      setError(copy.inputRequired);
      return;
    }

    setSubmitting(true);
    try {
      const payload = await generateComment({
        input: userInput,
        prompt_key: promptKey,
        persona_key: personaKey,
        model,
      });
      setOutput(payload.content || "");
      setProvider(payload.provider || "");
      setModelUsed(payload.model || "");
      setStatus(`${copy.modelUsed}: ${payload.model}`);
    } catch (exc) {
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

      <div className="card" style={{ marginTop: 14 }}>
        <div className="form-grid">
          <label className="field">
            <span>{copy.model}</span>
            <select
              className="input"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              disabled={loadingOptions || submitting}
            >
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

          <label className="field" style={{ gridColumn: "1 / -1" }}>
            <span>{copy.userInput}</span>
            <textarea
              className="input"
              rows={10}
              style={{ minHeight: 180 }}
              value={userInput}
              onChange={(event) => setUserInput(event.target.value)}
              placeholder={copy.userInputPlaceholder}
              disabled={submitting}
            />
          </label>
        </div>

        <div className="toolbar" style={{ marginTop: 10 }}>
          <button className="button" onClick={() => void onGenerate()} disabled={loadingOptions || submitting}>
            {submitting ? copy.generating : copy.generate}
          </button>
          <button className="button muted" onClick={() => void loadOptions()} disabled={submitting}>
            {copy.refreshOptions}
          </button>
        </div>
      </div>

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

      <div className="card-grid" style={{ marginTop: 14 }}>
        <div className="card">
          <h3>{copy.outputTitle}</h3>
          <div className="list" style={{ marginTop: 0 }}>
            <div>
              {copy.provider}: {provider || "-"}
            </div>
            <div>
              {copy.modelUsed}: {modelUsed || "-"}
            </div>
          </div>
          <div className="code" style={{ marginTop: 10, minHeight: 200 }}>
            {output || copy.outputPlaceholder}
          </div>
        </div>

        <div className="card">
          <h3>{copy.notesTitle}</h3>
          <ul className="list">
            <li>{copy.notesOne}</li>
            <li>{copy.notesTwo}</li>
            <li>{copy.notesThree}</li>
          </ul>
        </div>
      </div>
    </section>
  );
}
