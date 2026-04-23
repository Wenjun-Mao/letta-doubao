"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  LabelSchemaRecord,
  archiveLabelSchema,
  createLabelSchema,
  listLabelSchemas,
  purgeLabelSchema,
  restoreLabelSchema,
  updateLabelSchema,
} from "../../lib/api";
import { useI18n } from "../../lib/i18n";

const COPY = {
  en: {
    kicker: "Schema Workspace",
    title: "Label Schema Center",
    subtitle: "Manage Label Lab JSON schemas as workspace files with archive and restore.",
    includeArchived: "Include archived",
    refresh: "Refresh",
    createNew: "New",
    schemas: "Schemas",
    noSchemas: "No label schemas found.",
    editor: "Editor",
    key: "Key",
    label: "Label",
    description: "Description",
    schema: "JSON Schema",
    saveCreate: "Create",
    saveUpdate: "Update",
    archive: "Archive",
    restore: "Restore",
    purge: "Purge",
    openInLabelLab: "Open In Label Lab",
    archived: "Archived",
    active: "Active",
    readOnly: "Archived schemas are read-only. Restore first to edit.",
    selectHint: "Select a schema from the list, or create a new one.",
    confirmPurge: "Permanently purge this archived schema?",
  },
  zh: {
    kicker: "Schema 工作区",
    title: "标注 Schema 中心",
    subtitle: "以工作区文件方式管理 Label Lab JSON Schema，支持归档与恢复。",
    includeArchived: "包含已归档",
    refresh: "刷新",
    createNew: "新建",
    schemas: "Schema 列表",
    noSchemas: "没有找到标注 Schema。",
    editor: "编辑器",
    key: "键名",
    label: "标题",
    description: "描述",
    schema: "JSON Schema",
    saveCreate: "创建",
    saveUpdate: "更新",
    archive: "归档",
    restore: "恢复",
    purge: "彻底删除",
    openInLabelLab: "在标注实验室中打开",
    archived: "已归档",
    active: "生效中",
    readOnly: "已归档 Schema 为只读，请先恢复后再编辑。",
    selectHint: "请从列表选择 Schema，或创建新的 Schema。",
    confirmPurge: "确认彻底删除该归档 Schema 吗？",
  },
} as const;

function toErrorMessage(value: unknown): string {
  return value instanceof Error ? value.message : String(value);
}

function stringifySchema(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "{}";
  }
}

function parseSchema(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Schema must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

export default function SchemaCenterPage() {
  const { locale } = useI18n();
  const copy = COPY[locale];

  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [items, setItems] = useState<LabelSchemaRecord[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [editingExisting, setEditingExisting] = useState(false);
  const [draftKey, setDraftKey] = useState("");
  const [draftLabel, setDraftLabel] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [draftSchema, setDraftSchema] = useState("");

  const selected = useMemo(() => items.find((item) => item.key === selectedKey) || null, [items, selectedKey]);

  const resetDraft = () => {
    setSelectedKey("");
    setEditingExisting(false);
    setDraftKey("");
    setDraftLabel("");
    setDraftDescription("");
    setDraftSchema("");
  };

  const hydrateDraft = (item: LabelSchemaRecord) => {
    setSelectedKey(item.key);
    setEditingExisting(true);
    setDraftKey(item.key);
    setDraftLabel(item.label || "");
    setDraftDescription(item.description || "");
    setDraftSchema(stringifySchema(item.schema));
  };

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await listLabelSchemas(includeArchived);
      const nextItems = payload.items || [];
      setItems(nextItems);
      if (selectedKey) {
        const matched = nextItems.find((item) => item.key === selectedKey);
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
  }, [includeArchived]);

  const onSave = async () => {
    if (!draftKey.trim()) {
      setError(`${copy.key} is required.`);
      return;
    }
    if (!draftSchema.trim()) {
      setError(`${copy.schema} is required.`);
      return;
    }
    if (selected?.archived) {
      setError(copy.readOnly);
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      const schema = parseSchema(draftSchema);
      const payload = {
        key: draftKey.trim().toLowerCase(),
        label: draftLabel.trim() || undefined,
        description: draftDescription.trim() || undefined,
        schema,
      };
      const result = editingExisting
        ? await updateLabelSchema(draftKey.trim(), payload)
        : await createLabelSchema(payload);
      hydrateDraft(result);
      setStatus(`${result.key}: ${editingExisting ? copy.saveUpdate : copy.saveCreate} OK`);
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
      await archiveLabelSchema(selected.key);
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
      const result = await restoreLabelSchema(selected.key);
      hydrateDraft(result);
      setStatus(`${result.key}: ${copy.restore} OK`);
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const onPurge = async () => {
    if (!selected?.archived) {
      return;
    }
    if (typeof window !== "undefined" && !window.confirm(copy.confirmPurge)) {
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await purgeLabelSchema(selected.key);
      setStatus(`${selected.key}: ${copy.purge} OK`);
      resetDraft();
      await refresh();
    } catch (exc) {
      setError(toErrorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const labelLabHref = selectedKey ? `/label-lab?schemaKey=${encodeURIComponent(selectedKey)}` : "/label-lab";

  return (
    <section>
      <div className="kicker">{copy.kicker}</div>
      <h1 className="section-title">{copy.title}</h1>
      <p className="muted" style={{ maxWidth: 820 }}>{copy.subtitle}</p>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="toolbar" style={{ justifyContent: "space-between" }}>
          <label className="field" style={{ display: "inline-flex", flexDirection: "row", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} />
            <span>{copy.includeArchived}</span>
          </label>
          <div className="toolbar">
            <button className="button muted" onClick={() => void refresh()} disabled={loading || busy}>{copy.refresh}</button>
            <button className="button muted" onClick={resetDraft} disabled={busy}>{copy.createNew}</button>
            <Link className="button muted" href={labelLabHref}>{copy.openInLabelLab}</Link>
          </div>
        </div>
      </div>

      {error ? (
        <div className="card" style={{ marginTop: 12, borderColor: "#fecaca" }}>
          <p>{error}</p>
        </div>
      ) : null}

      {status ? (
        <div className="card" style={{ marginTop: 12, borderColor: "#bbf7d0" }}>
          <p>{status}</p>
        </div>
      ) : null}

      <div className="card-grid" style={{ marginTop: 14, alignItems: "start" }}>
        <div className="card">
          <h3>{copy.schemas}</h3>
          {loading ? <p className="muted">Loading...</p> : null}
          {!loading && items.length === 0 ? <p className="muted">{copy.noSchemas}</p> : null}
          <div className="studio-stack" style={{ marginTop: 8, maxHeight: 480, overflowY: "auto" }}>
            {items.map((item) => (
              <button
                key={item.key}
                type="button"
                className={item.key === selectedKey ? "tab-active" : "tab-item"}
                style={{ width: "100%", textAlign: "left" }}
                onClick={() => hydrateDraft(item)}
              >
                <div style={{ fontWeight: 700 }}>{item.label || item.key}</div>
                <div className="muted" style={{ fontSize: 12 }}>{item.key}</div>
                <div className="muted" style={{ fontSize: 12 }}>{item.archived ? copy.archived : copy.active}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="card">
          <h3>{copy.editor}</h3>
          {!selected && !editingExisting ? <p className="muted">{copy.selectHint}</p> : null}
          {selected?.archived ? <p className="muted">{copy.readOnly}</p> : null}

          <div className="form-grid" style={{ marginTop: 8 }}>
            <label className="field">
              <span>{copy.key}</span>
              <input className="input" value={draftKey} onChange={(event) => setDraftKey(event.target.value)} disabled={editingExisting} />
            </label>
            <label className="field">
              <span>{copy.label}</span>
              <input className="input" value={draftLabel} onChange={(event) => setDraftLabel(event.target.value)} />
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>{copy.description}</span>
              <input className="input" value={draftDescription} onChange={(event) => setDraftDescription(event.target.value)} />
            </label>
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>{copy.schema}</span>
              <textarea
                className="input"
                style={{ minHeight: 420, resize: "vertical", fontFamily: "Consolas, monospace" }}
                value={draftSchema}
                onChange={(event) => setDraftSchema(event.target.value)}
              />
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
          </div>
        </div>
      </div>
    </section>
  );
}
