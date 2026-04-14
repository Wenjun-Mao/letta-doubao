"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "../../lib/i18n";

const COPY = {
  en: {
    kicker: "Consolidated Module",
    title: "Prompt and Persona Lab",
    movedTitle: "Moved Into Prompt Center",
    movedText: "Prompt and persona CRUD workflows now live in Prompt Center. Redirecting now.",
    openButton: "Open Prompt Center",
  },
  zh: {
    kicker: "模块已合并",
    title: "提示词与 Persona 实验室",
    movedTitle: "已迁入提示词中心",
    movedText: "提示词与 Persona 的 CRUD 工作流现已迁至提示词中心，正在跳转。",
    openButton: "打开提示词中心",
  },
} as const;

export default function PromptPersonaLabPage() {
  const { locale } = useI18n();
  const copy = COPY[locale];
  const router = useRouter();

  useEffect(() => {
    router.replace("/prompt-center");
  }, [router]);

  return (
    <section>
      <div className="kicker">{copy.kicker}</div>
      <h1 className="section-title">{copy.title}</h1>
      <div className="card">
        <h3>{copy.movedTitle}</h3>
        <p>{copy.movedText}</p>
        <div className="toolbar" style={{ marginTop: 10 }}>
          <Link className="button" href="/prompt-center">
            {copy.openButton}
          </Link>
        </div>
      </div>
    </section>
  );
}
