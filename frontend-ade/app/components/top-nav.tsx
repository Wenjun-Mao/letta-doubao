"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import packageJson from "../../package.json";
import { useI18n } from "../../lib/i18n";

const NAV_ITEMS = [
  { href: "/", key: "dashboard" },
  { href: "/agent-studio", key: "agentStudio" },
  { href: "/comment-lab", key: "commentLab" },
  { href: "/prompt-center", key: "promptCenter" },
  { href: "/tool-center", key: "toolCenter" },
  { href: "/test-center", key: "testCenter" },
  { href: "/api-docs", key: "apiDocs" },
] as const;

const COPY = {
  en: {
    navAriaLabel: "ADE navigation",
    languageAriaLabel: "Language",
    releaseAriaLabel: "UI release",
    releaseTag: "UI",
    dashboard: "Dashboard",
    agentStudio: "Agent Studio",
    commentLab: "Comment Lab",
    promptCenter: "Prompt Center",
    toolCenter: "Tool Center",
    testCenter: "Test Center",
    apiDocs: "API Docs",
  },
  zh: {
    navAriaLabel: "ADE 导航",
    languageAriaLabel: "语言",
    releaseAriaLabel: "界面版本",
    releaseTag: "版本",
    dashboard: "仪表盘",
    agentStudio: "智能体工作台",
    commentLab: "评论实验室",
    promptCenter: "提示词中心",
    toolCenter: "工具中心",
    testCenter: "测试中心",
    apiDocs: "API 文档",
  },
} as const;

const PACKAGE_VERSION = typeof packageJson.version === "string" ? packageJson.version : "0.0.0";

function resolveReleaseLabel(): string {
  const version = (process.env.NEXT_PUBLIC_ADE_UI_VERSION || PACKAGE_VERSION).trim();
  const build = (process.env.NEXT_PUBLIC_ADE_UI_BUILD || "").trim();
  return build ? `v${version} (${build})` : `v${version}`;
}

function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function TopNav() {
  const { locale, setLocale } = useI18n();
  const copy = COPY[locale];
  const pathname = usePathname() || "/";
  const releaseLabel = resolveReleaseLabel();

  return (
    <div className="top-nav-group">
      <nav className="nav" aria-label={copy.navAriaLabel}>
        {NAV_ITEMS.map((item) => {
          const active = isActivePath(pathname, item.href);
          return (
            <Link className={active ? "nav-link nav-link-active" : "nav-link"} key={item.href} href={item.href}>
              {copy[item.key]}
            </Link>
          );
        })}
      </nav>
      <div className="release-chip" role="status" aria-label={copy.releaseAriaLabel} title={releaseLabel}>
        <span className="release-chip-tag">{copy.releaseTag}</span>
        <span className="release-chip-value">{releaseLabel}</span>
      </div>
      <div className="locale-switch" role="group" aria-label={copy.languageAriaLabel}>
        <button
          type="button"
          className={locale === "en" ? "locale-button locale-active" : "locale-button"}
          onClick={() => setLocale("en")}
        >
          EN
        </button>
        <button
          type="button"
          className={locale === "zh" ? "locale-button locale-active" : "locale-button"}
          onClick={() => setLocale("zh")}
        >
          中文
        </button>
      </div>
    </div>
  );
}