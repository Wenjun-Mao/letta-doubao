"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "../../lib/i18n";

const NAV_ITEMS = [
  { href: "/", key: "dashboard" },
  { href: "/agent-studio", key: "agentStudio" },
  { href: "/prompt-center", key: "promptCenter" },
  { href: "/tool-center", key: "toolCenter" },
  { href: "/test-center", key: "testCenter" },
  { href: "/api-docs", key: "apiDocs" },
] as const;

const COPY = {
  en: {
    navAriaLabel: "ADE navigation",
    languageAriaLabel: "Language",
    dashboard: "Dashboard",
    agentStudio: "Agent Studio",
    promptCenter: "Prompt Center",
    toolCenter: "Tool Center",
    testCenter: "Test Center",
    apiDocs: "API Docs",
  },
  zh: {
    navAriaLabel: "ADE 导航",
    languageAriaLabel: "语言",
    dashboard: "仪表盘",
    agentStudio: "智能体工作台",
    promptCenter: "提示词中心",
    toolCenter: "工具中心",
    testCenter: "测试中心",
    apiDocs: "API 文档",
  },
} as const;

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