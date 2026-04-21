"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fetchCapabilities, listAgents, listTestRuns } from "../lib/api";
import { useI18n } from "../lib/i18n";

const DOCS_HREF = "/api-docs";

const COPY = {
  en: {
    kicker: "ADE",
    title: "Agent Development Environment",
    intro: "This frontend provides the primary operator experience for Agent Platform workflows.",
    backendHealth: "Backend Health",
    checking: "Checking...",
    statusPrefix: "Status",
    platformEnabled: "Platform API enabled",
    strictMode: "Strict capabilities mode",
    operationalSnapshot: "Operational Snapshot",
    knownAgents: "Known agents",
    observedRuns: "Observed test runs",
    missingRequired: "Missing required capabilities",
    qualityGate: "Quality Gate",
    qualityGateSummary: "Backend E2E green plus ADE smoke suite green.",
    qualityGateHint: "Use this signal as the release-readiness baseline.",
    dashboardError: "Dashboard Error",
    openModule: "Open module",
    yes: "yes",
    no: "no",
    on: "on",
    off: "off",
    platformDisabled: "platform-disabled",
    degraded: "degraded",
    ready: "ready",
    modules: {
      agentStudioTitle: "Agent Studio",
      agentStudioDescription:
        "Runtime chat, prompt and persona editing, tool management, execution trace, and persistent state inspection.",
      commentLabTitle: "Comment Lab",
      commentLabDescription:
        "Stateless comment generation workspace with independent model, prompt, and persona controls.",
      promptCenterTitle: "Prompt Center",
      promptCenterDescription: "Manage system prompts and persona templates with workspace-persisted CRUD and archive/restore.",
      toolCenterTitle: "Tool Center",
      toolCenterDescription: "Create and maintain managed custom tools, then attach them in Agent Studio without restart.",
      testCenterTitle: "Test Center",
      testCenterDescription: "Create and monitor backend orchestrated checks and runners, including run artifacts.",
      apiDocsTitle: "API Docs",
      apiDocsDescription: "OpenAPI-backed interactive API documentation rendered directly inside ADE.",
    },
  },
  zh: {
    kicker: "ADE",
    title: "智能体开发环境",
    intro: "该前端提供 Agent Platform 工作流的主要运维操作体验。",
    backendHealth: "后端健康状态",
    checking: "检查中...",
    statusPrefix: "状态",
    platformEnabled: "Platform API 开关",
    strictMode: "严格能力模式",
    operationalSnapshot: "运行快照",
    knownAgents: "已知智能体数量",
    observedRuns: "已观察测试运行数",
    missingRequired: "缺失必需能力数",
    qualityGate: "质量门禁",
    qualityGateSummary: "后端 E2E 与 ADE 烟雾测试均已通过。",
    qualityGateHint: "该信号可作为发布就绪基线。",
    dashboardError: "仪表盘错误",
    openModule: "打开模块",
    yes: "是",
    no: "否",
    on: "开启",
    off: "关闭",
    platformDisabled: "platform-disabled",
    degraded: "degraded",
    ready: "ready",
    modules: {
      agentStudioTitle: "智能体工作台",
      agentStudioDescription: "支持运行时对话、提示词和 Persona 编辑、工具管理、执行轨迹及持久化状态查看。",
      commentLabTitle: "评论实验室",
      commentLabDescription: "独立的无状态评论生成空间，可分别控制模型、Prompt 与 Persona。",
      promptCenterTitle: "提示词中心",
      promptCenterDescription: "管理 System Prompt 与 Persona 模板，支持工作区持久化 CRUD 与归档恢复。",
      toolCenterTitle: "工具中心",
      toolCenterDescription: "创建并维护受管自定义工具，无需重启即可在智能体工作台挂载使用。",
      testCenterTitle: "测试中心",
      testCenterDescription: "创建并监控后端编排检查与运行任务，包括产物查看。",
      apiDocsTitle: "API 文档",
      apiDocsDescription: "基于 OpenAPI 的交互式 API 文档，直接在 ADE 内渲染。",
    },
  },
} as const;

function isExternalLink(href: string): boolean {
  return /^https?:\/\//i.test(href);
}

export default function DashboardPage() {
  const { locale } = useI18n();
  const copy = COPY[locale];

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [agentCount, setAgentCount] = useState(0);
  const [runCount, setRunCount] = useState(0);
  const [platformEnabled, setPlatformEnabled] = useState(false);
  const [strictMode, setStrictMode] = useState(false);
  const [missingCapabilities, setMissingCapabilities] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const [capabilities, agents, runs] = await Promise.all([
          fetchCapabilities(),
          listAgents(200),
          listTestRuns(),
        ]);

        if (cancelled) {
          return;
        }

        setPlatformEnabled(Boolean(capabilities.enabled));
        setStrictMode(Boolean(capabilities.strict_mode));
        setMissingCapabilities(Array.isArray(capabilities.missing_required) ? capabilities.missing_required : []);
        setAgentCount(Number(agents.total || 0));
        setRunCount(Array.isArray(runs.items) ? runs.items.length : 0);
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : String(exc));
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

  const healthLabel = useMemo(() => {
    if (!platformEnabled) {
      return copy.platformDisabled;
    }
    if (missingCapabilities.length > 0) {
      return copy.degraded;
    }
    return copy.ready;
  }, [copy.degraded, copy.platformDisabled, copy.ready, missingCapabilities.length, platformEnabled]);

  const modules = useMemo(
    () => [
      {
        title: copy.modules.agentStudioTitle,
        description: copy.modules.agentStudioDescription,
        href: "/agent-studio",
      },
      {
        title: copy.modules.commentLabTitle,
        description: copy.modules.commentLabDescription,
        href: "/comment-lab",
      },
      {
        title: copy.modules.promptCenterTitle,
        description: copy.modules.promptCenterDescription,
        href: "/prompt-center",
      },
      {
        title: copy.modules.toolCenterTitle,
        description: copy.modules.toolCenterDescription,
        href: "/tool-center",
      },
      {
        title: copy.modules.testCenterTitle,
        description: copy.modules.testCenterDescription,
        href: "/test-center",
      },
      {
        title: copy.modules.apiDocsTitle,
        description: copy.modules.apiDocsDescription,
        href: DOCS_HREF,
      },
    ],
    [copy.modules],
  );

  return (
    <section>
      <div className="kicker">{copy.kicker}</div>
      <h1 className="section-title">{copy.title}</h1>
      <p className="muted" style={{ maxWidth: 760 }}>
        {copy.intro}
      </p>

      <div className="card-grid" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>{copy.backendHealth}</h3>
          <p className="muted">{loading ? copy.checking : `${copy.statusPrefix}: ${healthLabel}`}</p>
          <ul className="list">
            <li>{copy.platformEnabled}: {platformEnabled ? copy.yes : copy.no}</li>
            <li>{copy.strictMode}: {strictMode ? copy.on : copy.off}</li>
          </ul>
        </div>

        <div className="card">
          <h3>{copy.operationalSnapshot}</h3>
          <ul className="list">
            <li>{copy.knownAgents}: {agentCount}</li>
            <li>{copy.observedRuns}: {runCount}</li>
            <li>{copy.missingRequired}: {missingCapabilities.length}</li>
          </ul>
        </div>

        <div className="card">
          <h3>{copy.qualityGate}</h3>
          <p className="muted">{copy.qualityGateSummary}</p>
          <p className="muted" style={{ marginTop: 8 }}>
            {copy.qualityGateHint}
          </p>
        </div>
      </div>

      {error ? (
        <div className="card" style={{ marginTop: 14, borderColor: "#fecaca" }}>
          <h3>{copy.dashboardError}</h3>
          <p className="muted">{error}</p>
        </div>
      ) : null}

      <div className="card-grid" style={{ marginTop: 18 }}>
        {modules.map((module) => {
          const content = (
            <>
              <h3>{module.title}</h3>
              <p>{module.description}</p>
              <p className="dashboard-module-hint">{copy.openModule}</p>
            </>
          );

          if (isExternalLink(module.href)) {
            return (
              <a key={module.title} className="card dashboard-module-link" href={module.href} target="_blank" rel="noreferrer">
                {content}
              </a>
            );
          }

          return (
            <Link key={module.title} className="card dashboard-module-link" href={module.href}>
              {content}
            </Link>
          );
        })}
      </div>
    </section>
  );
}
