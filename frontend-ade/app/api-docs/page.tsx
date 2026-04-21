"use client";

import { ApiReferenceReact } from "@scalar/api-reference-react";
import "@scalar/api-reference-react/style.css";

import { useI18n } from "../../lib/i18n";

const COPY = {
  en: {
    kicker: "API Reference",
    title: "Interactive API Documentation",
    description:
      "This page renders the platform OpenAPI schema directly inside ADE using Scalar. The schema switches with locale and defaults safely to English when a localized artifact is not available.",
    locale: "Locale",
    endpoint: "Spec endpoint",
    exporter: "Exporter",
    chineseSpec: "Chinese OpenAPI artifact",
    chineseDocs: "Chinese docs pages",
    manualGenerator: "Manual zh generator",
  },
  zh: {
    kicker: "API 参考",
    title: "交互式 API 文档",
    description:
      "该页面在 ADE 内直接渲染平台 OpenAPI 规范。规范会根据语言切换，并在中文产物缺失时安全回退到英文。",
    locale: "语言",
    endpoint: "规范端点",
    exporter: "导出脚本",
    chineseSpec: "中文 OpenAPI 产物",
    chineseDocs: "中文文档页面",
    manualGenerator: "手工中文生成脚本",
  },
} as const;

const OPENAPI_ENDPOINT = "/api/openapi";

export default function ApiDocsPage() {
  const { locale } = useI18n();
  const copy = COPY[locale];
  const localizedSpecUrl = `${OPENAPI_ENDPOINT}?locale=${locale}`;

  return (
    <section className="api-docs-section">
      <div className="kicker">{copy.kicker}</div>
      <h1 className="section-title">{copy.title}</h1>
      <div className="card">
        <p>{copy.description}</p>
        <ul className="list">
          <li>{copy.locale}: {locale === "zh" ? "zh" : "en"}</li>
          <li>{copy.endpoint}: {localizedSpecUrl}</li>
          <li>{copy.exporter}: scripts/export_openapi.py</li>
          <li>{copy.chineseSpec}: docs/openapi/agent-platform-openapi-zh.json</li>
          <li>{copy.chineseDocs}: docs/zh/index.mdx</li>
          <li>{copy.manualGenerator}: scripts/generate_openapi_zh_manual.py</li>
        </ul>
      </div>
      <div className="card api-docs-reference" style={{ marginTop: 12, padding: 0, overflow: "hidden" }}>
        <ApiReferenceReact
          key={locale}
          configuration={{
            url: localizedSpecUrl,
          }}
        />
      </div>
    </section>
  );
}
