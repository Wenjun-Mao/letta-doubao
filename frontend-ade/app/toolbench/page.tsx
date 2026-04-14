"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "../../lib/i18n";

const COPY = {
  en: {
    kicker: "Consolidated Module",
    title: "Toolbench",
    movedTitle: "Moved Into Tool Center",
    movedText: "Tool CRUD and lifecycle operations now live in Tool Center. Redirecting now.",
    openButton: "Open Tool Center",
  },
  zh: {
    kicker: "模块已合并",
    title: "工具台",
    movedTitle: "已迁入工具中心",
    movedText: "工具的 CRUD 与生命周期管理现已迁至工具中心，正在跳转。",
    openButton: "打开工具中心",
  },
} as const;

export default function ToolbenchPage() {
  const { locale } = useI18n();
  const copy = COPY[locale];
  const router = useRouter();

  useEffect(() => {
    router.replace("/tool-center");
  }, [router]);

  return (
    <section>
      <div className="kicker">{copy.kicker}</div>
      <h1 className="section-title">{copy.title}</h1>
      <div className="card">
        <h3>{copy.movedTitle}</h3>
        <p>{copy.movedText}</p>
        <div className="toolbar" style={{ marginTop: 10 }}>
          <Link className="button" href="/tool-center">
            {copy.openButton}
          </Link>
        </div>
      </div>
    </section>
  );
}
