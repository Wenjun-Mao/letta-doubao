import { OptionEntry } from "../../lib/api";

export const CHAT_MEMORY_DEFAULT_MODEL = "openai-proxy/dgx_vllm::qwen3.6-35b-a3b-fp8";
export const CHAT_MEMORY_DEFAULT_PROMPT = "chat_v20260516";
export const CHAT_MEMORY_DEFAULT_PERSONA = "chat_linxiaotang";
export const CHAT_MEMORY_DEFAULT_EMBEDDING = "letta/letta-free";
export const CHAT_MEMORY_FIXTURES = ["recent_user_chat_turns"];

export type ChatMemoryEvalCopy = {
  model: string;
  prompt: string;
  persona: string;
  embedding: string;
  fixture: string;
  rounds: string;
  timeoutSeconds: string;
  retryCount: string;
  judgeEnabled: string;
};

type Props = {
  copy: ChatMemoryEvalCopy;
  chatModels: OptionEntry[];
  chatPrompts: OptionEntry[];
  chatPersonas: OptionEntry[];
  chatEmbeddings: OptionEntry[];
  evalModel: string;
  evalPromptKey: string;
  evalPersonaKey: string;
  evalEmbedding: string;
  evalFixtureKey: string;
  evalRounds: string;
  evalTimeoutSeconds: string;
  evalRetryCount: string;
  evalJudgeEnabled: boolean;
  setEvalModel: (value: string) => void;
  setEvalPromptKey: (value: string) => void;
  setEvalPersonaKey: (value: string) => void;
  setEvalEmbedding: (value: string) => void;
  setEvalFixtureKey: (value: string) => void;
  setEvalRounds: (value: string) => void;
  setEvalTimeoutSeconds: (value: string) => void;
  setEvalRetryCount: (value: string) => void;
  setEvalJudgeEnabled: (value: boolean) => void;
};

export function optionLabel(option: OptionEntry): string {
  const key = String(option.key || "").trim();
  const label = String(option.label || "").trim();
  return label && label !== key ? `${label} (${key})` : key;
}

export function chooseAvailable(current: string, options: OptionEntry[], preferred: string): string {
  const keys = new Set(options.map((item) => String(item.key || "").trim()).filter(Boolean));
  if (current && keys.has(current)) {
    return current;
  }
  if (preferred && keys.has(preferred)) {
    return preferred;
  }
  return options[0]?.key || current || preferred;
}

export function ChatMemoryEvalFields(props: Props) {
  const copy = props.copy;
  return (
    <>
      <label className="field">
        <span>{copy.model}</span>
        <select className="input" value={props.evalModel} onChange={(e) => props.setEvalModel(e.target.value)}>
          {props.chatModels.map((item) => (
            <option key={item.key} value={item.key}>
              {optionLabel(item)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{copy.prompt}</span>
        <select className="input" value={props.evalPromptKey} onChange={(e) => props.setEvalPromptKey(e.target.value)}>
          {props.chatPrompts.map((item) => (
            <option key={item.key} value={item.key}>
              {optionLabel(item)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{copy.persona}</span>
        <select className="input" value={props.evalPersonaKey} onChange={(e) => props.setEvalPersonaKey(e.target.value)}>
          {props.chatPersonas.map((item) => (
            <option key={item.key} value={item.key}>
              {optionLabel(item)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{copy.embedding}</span>
        <select className="input" value={props.evalEmbedding} onChange={(e) => props.setEvalEmbedding(e.target.value)}>
          {props.chatEmbeddings.map((item) => (
            <option key={item.key} value={item.key}>
              {optionLabel(item)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{copy.fixture}</span>
        <select className="input" value={props.evalFixtureKey} onChange={(e) => props.setEvalFixtureKey(e.target.value)}>
          {CHAT_MEMORY_FIXTURES.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{copy.rounds}</span>
        <input className="input" value={props.evalRounds} onChange={(e) => props.setEvalRounds(e.target.value)} />
      </label>
      <label className="field">
        <span>{copy.timeoutSeconds}</span>
        <input
          className="input"
          value={props.evalTimeoutSeconds}
          onChange={(e) => props.setEvalTimeoutSeconds(e.target.value)}
        />
      </label>
      <label className="field">
        <span>{copy.retryCount}</span>
        <input className="input" value={props.evalRetryCount} onChange={(e) => props.setEvalRetryCount(e.target.value)} />
      </label>
      <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <input
          type="checkbox"
          checked={props.evalJudgeEnabled}
          onChange={(e) => props.setEvalJudgeEnabled(e.target.checked)}
        />
        <span>{copy.judgeEnabled}</span>
      </label>
    </>
  );
}
