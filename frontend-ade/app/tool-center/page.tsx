"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  ToolCenterItem,
  archiveToolCenterTool,
  createToolCenterTool,
  getToolCenterTool,
  listToolCenterTools,
  purgeToolCenterTool,
  restoreToolCenterTool,
  updateToolCenterTool,
} from "../../lib/api";
import { useI18n } from "../../lib/i18n";

type ViewMode = "create" | "edit";

function toErrorMessage(value: unknown): string {
  return value instanceof Error ? value.message : String(value);
}

const COPY = {
  en: {
    kicker: "Custom Tool Workspace",
    title: "Tool Center",
    subtitle:
      "CRUD managed custom tools with workspace persistence and instant Agent Studio availability. Built-ins stay read-only.",
    includeArchived: "Include archived",
    includeBuiltin: "Include built-ins",
    includeSourceInList: "Include source in list",
    search: "Search",
    refresh: "Refresh",
    createNew: "New custom tool",
    attachStudio: "Open Agent Studio (Tools)",
    slug: "Slug",
    description: "Description",
    tags: "Tags (comma separated)",
    source: "Python source",
    create: "Create",
    update: "Update",
    archive: "Archive",
    restore: "Restore",
    purge: "Purge",
    noResults: "No tools matched the current filters.",
    readOnlyBuiltin: "Built-in tool (read-only)",
    managedTool: "Managed custom tool",
    archivedBadge: "Archived",
    activeBadge: "Active",
    confirmPurge: "Permanently purge this archived custom tool?",
  },
  zh: {
    kicker: "自定义工具工作区",
    title: "工具中心",
    subtitle: "对受管自定义工具进行 CRUD，持久化到工作区并即时可用于智能体工作台。内置工具保持只读。",
    includeArchived: "包含已归档",
    includeBuiltin: "包含内置工具",
    includeSourceInList: "列表中包含源码",
    search: "搜索",
    refresh: "刷新",
    createNew: "新建自定义工具",
    attachStudio: "打开智能体工作台（Tools）",
    slug: "Slug",
    description: "描述",
    tags: "标签（逗号分隔）",
    source: "Python 源码",
    create: "创建",
    update: "更新",
    archive: "归档",
    restore: "恢复",
    purge: "彻底删除",
    noResults: "当前筛选下没有工具。",
    readOnlyBuiltin: "内置工具（只读）",
    managedTool: "受管自定义工具",
    archivedBadge: "已归档",
    activeBadge: "生效中",
    confirmPurge: "确认彻底删除该归档自定义工具吗？",
  },
} as const;

export default function ToolCenterPage() {
  const { locale } = useI18n();
  const copy = COPY[locale];

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const [includeArchived, setIncludeArchived] = useState(false);
  const [includeBuiltin, setIncludeBuiltin] = useState(true);
  const [includeSourceInList, setIncludeSourceInList] = useState(false);
  const [search, setSearch] = useState("");

  const [items, setItems] = useState<ToolCenterItem[]>([]);
  const [selectedId, setSelectedId] = useState("");

  const [mode, setMode] = useState<ViewMode>("create");
  const [draftSlug, setDraftSlug] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [draftTags, setDraftTags] = useState("");
  const [draftSource, setDraftSource] = useState("def my_custom_tool(input_text: str) -> str:\n    \"\"\"Describe what this tool does.\"\"\"\n    return f\"echo: {input_text}\"\n");

  const selected = useMemo(() => {
    return items.find((item) => (item.slug ? item.slug === selectedId : item.tool_id === selectedId)) || null;
  }, [items, selectedId]);

  const primaryDisabled =
    busy ||
    loading ||
    (mode === "create"
      ? Boolean(selected && !selected.managed)
      : Boolean(!selected?.managed || selected.archived));

  const resetDraft = () => {
    setMode("create");
    setSelectedId("");
    setDraftSlug("");
    setDraftDescription("");
    setDraftTags("");
    setDraftSource("def my_custom_tool(input_text: str) -> str:\n    \"\"\"Describe what this tool does.\"\"\"\n    return f\"echo: {input_text}\"\n");
  };

  const hydrateDraft = (item: ToolCenterItem, withSource = true) => {
    setMode(item.managed ? "edit" : "create");
    setSelectedId(item.slug || item.tool_id);
    setDraftSlug(item.slug || "");
    setDraftDescription(item.description || "");
    setDraftTags((item.tags || []).join(", "));
    if (withSource) {
      setDraftSource(item.source_code || "");
    }
  };

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await listToolCenterTools({
        includeArchived,
        includeBuiltin,
        includeSource: includeSourceInList,
        search,
      });
      setItems(payload.items || []);

      if (selectedId) {
        const stillThere = (payload.items || []).find((item) => (item.slug ? item.slug === selectedId : item.tool_id === selectedId));
        if (stillThere) {
          if (stillThere.managed && stillThere.slug && !includeSourceInList) {
            const detail = await getToolCenterTool(stillThere.slug, true);
            hydrateDraft(detail, true);
          } else {
            hydrateDraft(stillThere, true);
          }
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
  }, [includeArchived, includeBuiltin, includeSourceInList]);

  const onSelect = async (item: ToolCenterItem) => {
    setError("");
    setStatus("");

    if (item.managed && item.slug) {
      try {
        const detail = await getToolCenterTool(item.slug, true);
        hydrateDraft(detail, true);
      } catch (exc) {
        setError(toErrorMessage(exc));
      }
      return;
    }

    hydrateDraft(item, false);
  };

  const parsedTags = useMemo(() => {
    return draftTags
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
  }, [draftTags]);

  const onCreate = async () => {
    if (!draftSlug.trim()) {
      setError(`${copy.slug} is required.`);
      return;
    }
    if (!draftSource.trim()) {
      setError(`${copy.source} is required.`);
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      const created = await createToolCenterTool({
        slug: draftSlug.trim(),
        source_code: draftSource,
        description: draftDescription.trim(),
        tags: parsedTags,
      });
      hydrateDraft(created, true);
      setStatus(`${created.slug || created.name}: ${copy.create} OK`);
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onUpdate = async () => {
    if (!selected?.managed || !selected.slug) {
      return;
    }
    if (selected.archived) {
      setError(`${copy.archivedBadge}: restore before update.`);
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      const updated = await updateToolCenterTool(selected.slug, {
        source_code: draftSource,
        description: draftDescription.trim(),
        tags: parsedTags,
      });
      hydrateDraft(updated, true);
      setStatus(`${updated.slug || updated.name}: ${copy.update} OK`);
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onArchive = async () => {
    if (!selected?.managed || !selected.slug || selected.archived) {
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const archived = await archiveToolCenterTool(selected.slug);
      hydrateDraft(archived, true);
      setStatus(`${archived.slug || archived.name}: ${copy.archive} OK`);
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onRestore = async () => {
    if (!selected?.managed || !selected.slug || !selected.archived) {
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const restored = await restoreToolCenterTool(selected.slug);
      hydrateDraft(restored, true);
      setStatus(`${restored.slug || restored.name}: ${copy.restore} OK`);
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onPurge = async () => {
    if (!selected?.managed || !selected.slug || !selected.archived) {
      return;
    }
    if (typeof window !== "undefined" && !window.confirm(copy.confirmPurge)) {
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      await purgeToolCenterTool(selected.slug);
      setStatus(`${selected.slug}: ${copy.purge} OK`);
      resetDraft();
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <div className="kicker">{copy.kicker}</div>
      <h1 className="section-title">{copy.title}</h1>
      <p className="muted" style={{ maxWidth: 840 }}>{copy.subtitle}</p>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="toolbar" style={{ justifyContent: "space-between" }}>
          <div className="toolbar" style={{ flexWrap: "wrap" }}>
            <label className="field" style={{ display: "inline-flex", flexDirection: "row", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
              <span>{copy.includeArchived}</span>
            </label>
            <label className="field" style={{ display: "inline-flex", flexDirection: "row", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={includeBuiltin} onChange={(e) => setIncludeBuiltin(e.target.checked)} />
              <span>{copy.includeBuiltin}</span>
            </label>
            <label className="field" style={{ display: "inline-flex", flexDirection: "row", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={includeSourceInList} onChange={(e) => setIncludeSourceInList(e.target.checked)} />
              <span>{copy.includeSourceInList}</span>
            </label>
          </div>

          <div className="toolbar">
            <input
              className="input"
              style={{ minWidth: 220 }}
              placeholder={copy.search}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button className="button muted" onClick={() => void refresh()} disabled={loading || busy}>{copy.refresh}</button>
            <button className="button muted" onClick={resetDraft} disabled={busy}>{copy.createNew}</button>
            <Link className="button muted" href="/agent-studio?focus=tools">{copy.attachStudio}</Link>
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
          <h3>Tools</h3>
          {loading ? <p className="muted">Loading...</p> : null}
          {!loading && items.length === 0 ? <p className="muted">{copy.noResults}</p> : null}
          <div className="studio-stack" style={{ marginTop: 8, maxHeight: 540, overflowY: "auto" }}>
            {items.map((item) => {
              const id = item.slug || item.tool_id;
              return (
                <button
                  key={id}
                  type="button"
                  className={id === selectedId ? "tab-active" : "tab-item"}
                  style={{ width: "100%", textAlign: "left" }}
                  onClick={() => void onSelect(item)}
                >
                  <div style={{ fontWeight: 700 }}>{item.name || item.slug || item.tool_id}</div>
                  <div className="muted" style={{ fontSize: 12 }}>{item.slug || item.tool_id}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {item.managed ? copy.managedTool : copy.readOnlyBuiltin} | {item.archived ? copy.archivedBadge : copy.activeBadge}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="card">
          <h3>{mode === "create" ? copy.createNew : selected?.name || "Tool"}</h3>

          <div className="form-grid" style={{ marginTop: 8 }}>
            <label className="field">
              <span>{copy.slug}</span>
              <input className="input" value={draftSlug} onChange={(e) => setDraftSlug(e.target.value)} disabled={mode === "edit"} />
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>{copy.description}</span>
              <textarea
                className="input"
                style={{ minHeight: 88, resize: "vertical" }}
                value={draftDescription}
                onChange={(e) => setDraftDescription(e.target.value)}
                disabled={selected ? Boolean(!selected.managed || selected.archived) : false}
              />
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>{copy.tags}</span>
              <input className="input" value={draftTags} onChange={(e) => setDraftTags(e.target.value)} disabled={selected ? Boolean(!selected.managed || selected.archived) : false} />
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>{copy.source}</span>
              <textarea
                className="input"
                style={{ minHeight: 340, resize: "vertical", fontFamily: "Consolas, monospace" }}
                value={draftSource}
                onChange={(e) => setDraftSource(e.target.value)}
                disabled={selected ? Boolean(!selected.managed || selected.archived) : false}
              />
            </label>
          </div>

          <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="button" onClick={() => void (mode === "create" ? onCreate() : onUpdate())} disabled={primaryDisabled}>
              {busy ? "..." : mode === "create" ? copy.create : copy.update}
            </button>
            <button className="button muted" onClick={() => void onArchive()} disabled={busy || !selected?.managed || Boolean(selected?.archived)}>
              {copy.archive}
            </button>
            <button className="button muted" onClick={() => void onRestore()} disabled={busy || !selected?.managed || !Boolean(selected?.archived)}>
              {copy.restore}
            </button>
            <button className="button danger" onClick={() => void onPurge()} disabled={busy || !selected?.managed || !Boolean(selected?.archived)}>
              {copy.purge}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
