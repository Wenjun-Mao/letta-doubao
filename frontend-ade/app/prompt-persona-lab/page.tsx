"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function PromptPersonaLabPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/agent-studio?focus=prompt");
  }, [router]);

  return (
    <section>
      <div className="kicker">Consolidated Module</div>
      <h1 className="section-title">Prompt and Persona Lab</h1>
      <div className="card">
        <h3>Moved Into Agent Studio</h3>
        <p>
          Prompt and persona editing is now part of the unified Agent Studio inspector.
          Redirecting now.
        </p>
        <div className="toolbar" style={{ marginTop: 10 }}>
          <Link className="button" href="/agent-studio?focus=prompt">
            Open Agent Studio (Prompt Tab)
          </Link>
        </div>
      </div>
    </section>
  );
}
