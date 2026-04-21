"use client";

import { useI18n } from "../../lib/i18n";

const COPY = {
  en: {
    kicker: "Docs",
    title: "Documentation Entry",
    description: "This local route tracks the self-hosted API docs pipeline used by ADE.",
    openapiArtifact: "OpenAPI source artifact",
    frontendArtifact: "Frontend OpenAPI artifact",
    chineseOpenapiArtifact: "Chinese OpenAPI artifact",
    chineseDocsEntry: "Chinese docs entry",
    exporterScript: "Exporter script",
    manualZhScript: "Manual zh script",
  },
  zh: {
    kicker: "文档",
    title: "文档入口",
    description: "该本地路由用于跟踪 ADE 的自托管 API 文档流水线。",
    openapiArtifact: "OpenAPI 源产物",
    frontendArtifact: "前端 OpenAPI 产物",
    chineseOpenapiArtifact: "中文 OpenAPI 产物",
    chineseDocsEntry: "中文文档入口",
    exporterScript: "导出脚本",
    manualZhScript: "手工中文脚本",
  },
} as const;

export default function LocalDocsPage() {
  const { locale } = useI18n();
  const copy = COPY[locale];

  return (
    <section>
      <div className="kicker">{copy.kicker}</div>
      <h1 className="section-title">{copy.title}</h1>
      <div className="card">
        <p className="muted">{copy.description}</p>
        <ul className="list">
          <li>{copy.openapiArtifact}: docs/openapi/agent-platform-openapi.json</li>
          <li>{copy.frontendArtifact}: frontend-ade/public/openapi/agent-platform-openapi.json</li>
          <li>{copy.chineseOpenapiArtifact}: docs/openapi/agent-platform-openapi-zh.json</li>
          <li>{copy.chineseDocsEntry}: docs/zh/index.mdx</li>
          <li>{copy.exporterScript}: scripts/export_openapi.py</li>
          <li>{copy.manualZhScript}: scripts/generate_openapi_zh_manual.py</li>
        </ul>
      </div>
    </section>
  );
}
