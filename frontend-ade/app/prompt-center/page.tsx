"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  PromptTemplateRecord,
  Scenario,
  archivePersonaTemplate,
  archivePromptTemplate,
  createPersonaTemplate,
  createPromptTemplate,
  listPersonaTemplates,
  listPromptTemplates,
  purgePersonaTemplate,
  purgePromptTemplate,
  restorePersonaTemplate,
  restorePromptTemplate,
  updatePersonaTemplate,
  updatePromptTemplate,
} from "../../lib/api";
import { useI18n } from "../../lib/i18n";

type CenterTab = "prompts" | "personas";

function toErrorMessage(value: unknown): string {
  return value instanceof Error ? value.message : String(value);
}

function normalizeScenarioKey(key: string, scenario: Scenario): string {
  const normalized = key.trim().toLowerCase();
  if (!normalized) {
    return "";
  }

  const withoutScenarioPrefix = normalized.replace(/^(chat|comment|label)_/, "");
  return `${scenario}_${withoutScenarioPrefix}`;
}

const COPY = {
  en: {
    kicker: "Template Workspace",
    title: "Prompt Center",
    subtitle:
      "Manage system prompts and persona templates as workspace files, with archive/restore and immediate availability.",
    promptsTab: "System Prompts",
    personasTab: "Persona Prompts",
    chatScenario: "Chat",
    commentScenario: "Comment",
    labelScenario: "Label",
    scenarioLabel: "Scenario",
    includeArchived: "Include archived",
    refresh: "Refresh",
    createNew: "New",
    key: "Key",
    label: "Label (optional)",
    description: "Description (optional)",
    content: "Content",
    saveCreate: "Create",
    saveUpdate: "Update",
    archive: "Archive",
    restore: "Restore",
    purge: "Purge",
    openInAgentStudio: "Open In Agent Studio",
    openInCommentLab: "Open In Comment Lab",
    openInLabelLab: "Open In Label Lab",
    noTemplates: "No templates found for current filter.",
    activeList: "Templates",
    editor: "Editor",
    archivedBadge: "Archived",
    activeBadge: "Active",
    saveDisabledArchived: "Archived templates are read-only. Restore first to edit.",
    confirmPurge: "Permanently purge this archived template?",
    selectHint: "Select a template from the list, or create a new one.",
  },
  zh: {
    kicker: "模板工作区",
    title: "提示词中心",
    subtitle: "将 System Prompt 与 Persona 模板作为工作区文件管理，支持归档恢复并即时生效。",
    promptsTab: "System Prompt",
    personasTab: "Persona Prompt",
    chatScenario: "Chat",
    commentScenario: "Comment",
    labelScenario: "Label",
    scenarioLabel: "场景",
    includeArchived: "包含已归档",
    refresh: "刷新",
    createNew: "新建",
    key: "键名",
    label: "标题（可选）",
    description: "描述（可选）",
    content: "内容",
    saveCreate: "创建",
    saveUpdate: "更新",
    archive: "归档",
    restore: "恢复",
    purge: "彻底删除",
    openInAgentStudio: "在智能体工作台中打开",
    openInCommentLab: "在评论实验室中打开",
    openInLabelLab: "在标注实验室中打开",
    noTemplates: "当前筛选下没有模板。",
    activeList: "模板列表",
    editor: "编辑器",
    archivedBadge: "已归档",
    activeBadge: "生效中",
    saveDisabledArchived: "已归档模板为只读，请先恢复后再编辑。",
    confirmPurge: "确认彻底删除该归档模板吗？",
    selectHint: "请先从左侧选择模板，或创建新模板。",
  },
} as const;

export default function PromptCenterPage() {
  const { locale } = useI18n();
  const copy = COPY[locale];

  const [tab, setTab] = useState<CenterTab>("prompts");
  const [scenario, setScenario] = useState<Scenario>("chat");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const [promptItems, setPromptItems] = useState<PromptTemplateRecord[]>([]);
  const [personaItems, setPersonaItems] = useState<PromptTemplateRecord[]>([]);

  const [selectedKey, setSelectedKey] = useState("");
  const [editingExisting, setEditingExisting] = useState(false);

  const [draftKey, setDraftKey] = useState("");
  const [draftLabel, setDraftLabel] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [draftContent, setDraftContent] = useState("");

  const activeItems = tab === "prompts" ? promptItems : personaItems;

  const selected = useMemo(() => {
    return activeItems.find((item) => item.key === selectedKey) || null;
  }, [activeItems, selectedKey]);

  const activePromptKeys = useMemo(
    () => promptItems.filter((item) => !item.archived).map((item) => item.key),
    [promptItems],
  );

  const activePersonaKeys = useMemo(
    () => personaItems.filter((item) => !item.archived).map((item) => item.key),
    [personaItems],
  );

  const resetDraft = () => {
    setSelectedKey("");
    setEditingExisting(false);
    setDraftKey("");
    setDraftLabel("");
    setDraftDescription("");
    setDraftContent("");
  };

  const hydrateDraft = (item: PromptTemplateRecord) => {
    setSelectedKey(item.key);
    setEditingExisting(true);
    setDraftKey(item.key);
    setDraftLabel(item.label || "");
    setDraftDescription(item.description || "");
    setDraftContent(item.content || "");
  };

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const [promptPayload, personaPayload] = await Promise.all([
        listPromptTemplates(includeArchived, scenario),
        listPersonaTemplates(includeArchived, scenario),
      ]);

      setPromptItems(promptPayload.items || []);
      setPersonaItems(personaPayload.items || []);

      if (selectedKey) {
        const currentList = tab === "prompts" ? promptPayload.items || [] : personaPayload.items || [];
        const matched = currentList.find((item) => item.key === selectedKey);
        if (matched) {
          hydrateDraft(matched);
        } else {
          resetDraft();
        }
      }
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [includeArchived, scenario]);

  useEffect(() => {
    resetDraft();
    setError("");
    setStatus("");
  }, [tab, scenario]);

  useEffect(() => {
    if (scenario === "label" && tab === "personas") {
      setTab("prompts");
    }
  }, [scenario, tab]);

  const onSave = async () => {
    if (!draftKey.trim()) {
      setError(`${copy.key} is required.`);
      return;
    }
    if (!draftContent.trim()) {
      setError(`${copy.content} is required.`);
      return;
    }
    if (selected?.archived) {
      setError(copy.saveDisabledArchived);
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      const resolvedKey = editingExisting ? draftKey.trim() : normalizeScenarioKey(draftKey, scenario);
      setDraftKey(resolvedKey);

      const payload = {
        scenario,
        key: resolvedKey,
        label: draftLabel.trim() || undefined,
        description: draftDescription.trim() || undefined,
        content: draftContent,
      };

      const result =
        tab === "prompts"
          ? editingExisting
            ? await updatePromptTemplate(draftKey.trim(), payload)
            : await createPromptTemplate(payload)
          : editingExisting
            ? await updatePersonaTemplate(draftKey.trim(), payload)
            : await createPersonaTemplate(payload);

      hydrateDraft(result);
      setStatus(`${tab === "prompts" ? copy.promptsTab : copy.personasTab}: ${editingExisting ? copy.saveUpdate : copy.saveCreate} OK`);
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onArchive = async () => {
    if (!selected) {
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      if (tab === "prompts") {
        await archivePromptTemplate(selected.key, selected.scenario);
      } else {
        await archivePersonaTemplate(selected.key, selected.scenario);
      }
      setStatus(`${selected.key}: ${copy.archive} OK`);
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onRestore = async () => {
    if (!selected) {
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const result =
        tab === "prompts"
          ? await restorePromptTemplate(selected.key, selected.scenario)
          : await restorePersonaTemplate(selected.key, selected.scenario);
      hydrateDraft(result);
      setStatus(`${selected.key}: ${copy.restore} OK`);
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onPurge = async () => {
    if (!selected || !selected.archived) {
      return;
    }
    if (typeof window !== "undefined" && !window.confirm(copy.confirmPurge)) {
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      if (tab === "prompts") {
        await purgePromptTemplate(selected.key, selected.scenario);
      } else {
        await purgePersonaTemplate(selected.key, selected.scenario);
      }
      setStatus(`${selected.key}: ${copy.purge} OK`);
      resetDraft();
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const selectedScenario = selected?.scenario || scenario;

  const workspaceHref = useMemo(() => {
    const promptKey = tab === "prompts" ? selected?.key || activePromptKeys[0] || "" : activePromptKeys[0] || "";
    const personaKey = tab === "personas" ? selected?.key || activePersonaKeys[0] || "" : activePersonaKeys[0] || "";
    const params = new URLSearchParams();
    if (promptKey) {
      params.set("promptKey", promptKey);
    }
    if (personaKey && selectedScenario !== "label") {
      params.set("personaKey", personaKey);
    }
    if (selectedScenario === "comment") {
      return `/comment-lab?${params.toString()}`;
    }
    if (selectedScenario === "label") {
      return `/label-lab?${params.toString()}`;
    }
    params.set("focus", "model");
    return `/agent-studio?${params.toString()}`;
  }, [activePersonaKeys, activePromptKeys, scenario, selected?.key, selectedScenario, tab]);

  const workspaceLabel =
    selectedScenario === "comment"
      ? copy.openInCommentLab
      : selectedScenario === "label"
        ? copy.openInLabelLab
        : copy.openInAgentStudio;

  return (
    <section>
      <div className="kicker">{copy.kicker}</div>
      <h1 className="section-title">{copy.title}</h1>
      <p className="muted" style={{ maxWidth: 840 }}>{copy.subtitle}</p>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="toolbar" style={{ justifyContent: "space-between" }}>
          <div className="toolbar">
            <button className={tab === "prompts" ? "tab-active" : "tab-item"} onClick={() => setTab("prompts")}>{copy.promptsTab}</button>
            {scenario !== "label" ? (
              <button className={tab === "personas" ? "tab-active" : "tab-item"} onClick={() => setTab("personas")}>{copy.personasTab}</button>
            ) : null}
          </div>

          <div className="toolbar">
            <span className="muted" style={{ fontSize: 12 }}>{copy.scenarioLabel}</span>
            <button className={scenario === "chat" ? "tab-active" : "tab-item"} onClick={() => setScenario("chat")}>{copy.chatScenario}</button>
            <button className={scenario === "comment" ? "tab-active" : "tab-item"} onClick={() => setScenario("comment")}>{copy.commentScenario}</button>
            <button className={scenario === "label" ? "tab-active" : "tab-item"} onClick={() => setScenario("label")}>{copy.labelScenario}</button>
          </div>

          <div className="toolbar">
            <label className="field" style={{ display: "inline-flex", flexDirection: "row", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
              <span>{copy.includeArchived}</span>
            </label>
            <button className="button muted" onClick={() => void refresh()} disabled={loading || busy}>{copy.refresh}</button>
            <button className="button muted" onClick={resetDraft} disabled={busy}>{copy.createNew}</button>
          </div>
        </div>
      </div>

      {error ? (
        <div className="card" style={{ marginTop: 12, borderColor: "#fecaca" }}>
          <h3>Error</h3>
          <p className="muted">{error}</p>
        </div>
      ) : null}

      {status ? (
        <div className="card" style={{ marginTop: 12, borderColor: "#bbf7d0" }}>
          <h3>Status</h3>
          <p className="muted">{status}</p>
        </div>
      ) : null}

      <div className="card-grid" style={{ marginTop: 14, alignItems: "start" }}>
        <div className="card">
          <h3>{copy.activeList}</h3>
          {loading ? <p className="muted">Loading...</p> : null}
          {!loading && activeItems.length === 0 ? <p className="muted">{copy.noTemplates}</p> : null}
          <div className="studio-stack" style={{ marginTop: 8, maxHeight: 480, overflowY: "auto" }}>
            {activeItems.map((item) => (
              <button
                key={item.key}
                type="button"
                className={item.key === selectedKey ? "tab-active" : "tab-item"}
                style={{ width: "100%", textAlign: "left" }}
                onClick={() => hydrateDraft(item)}
              >
                <div style={{ fontWeight: 700 }}>{item.label || item.key}</div>
                <div className="muted" style={{ fontSize: 12 }}>{item.key}</div>
                <div className="muted" style={{ fontSize: 12 }}>{item.scenario}</div>
                <div className="muted" style={{ fontSize: 12 }}>{item.archived ? copy.archivedBadge : copy.activeBadge}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="card">
          <h3>{copy.editor}</h3>
          {!selected && !editingExisting ? <p className="muted">{copy.selectHint}</p> : null}
          {selected?.archived ? <p className="muted">{copy.saveDisabledArchived}</p> : null}

          <div className="form-grid" style={{ marginTop: 8 }}>
            <label className="field">
              <span>{copy.scenarioLabel}</span>
              <input className="input" value={scenario} disabled />
            </label>
            <label className="field">
              <span>{copy.key}</span>
              <input
                className="input"
                value={draftKey}
                onChange={(e) => setDraftKey(e.target.value)}
                onBlur={(e) => {
                  if (!editingExisting) {
                    setDraftKey(normalizeScenarioKey(e.target.value, scenario));
                  }
                }}
                disabled={editingExisting}
              />
            </label>
            <label className="field">
              <span>{copy.label}</span>
              <input className="input" value={draftLabel} onChange={(e) => setDraftLabel(e.target.value)} />
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>{copy.description}</span>
              <input className="input" value={draftDescription} onChange={(e) => setDraftDescription(e.target.value)} />
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>{copy.content}</span>
              <textarea className="input" style={{ minHeight: 320, resize: "vertical", fontFamily: "Consolas, monospace" }} value={draftContent} onChange={(e) => setDraftContent(e.target.value)} />
            </label>
          </div>

          <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="button" onClick={() => void onSave()} disabled={busy || loading || Boolean(selected?.archived)}>
              {busy ? "..." : editingExisting ? copy.saveUpdate : copy.saveCreate}
            </button>
            <button className="button muted" onClick={() => void onArchive()} disabled={busy || !selected || Boolean(selected.archived)}>
              {copy.archive}
            </button>
            <button className="button muted" onClick={() => void onRestore()} disabled={busy || !selected || !Boolean(selected.archived)}>
              {copy.restore}
            </button>
            <button className="button danger" onClick={() => void onPurge()} disabled={busy || !selected || !Boolean(selected.archived)}>
              {copy.purge}
            </button>
            <Link className="button muted" href={workspaceHref}>{workspaceLabel}</Link>
          </div>
        </div>
      </div>
    </section>
  );
}
