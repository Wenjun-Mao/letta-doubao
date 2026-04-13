"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ToolbenchPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/agent-studio?focus=tools");
  }, [router]);

  return (
    <section>
      <div className="kicker">Consolidated Module</div>
      <h1 className="section-title">Toolbench</h1>
      <div className="card">
        <h3>Moved Into Agent Studio</h3>
        <p>
          Tool discovery and attach/detach flows now live in the Agent Studio tools tab.
          Redirecting now.
        </p>
        <div className="toolbar" style={{ marginTop: 10 }}>
          <Link className="button" href="/agent-studio?focus=tools">
            Open Agent Studio (Tools Tab)
          </Link>
        </div>
      </div>
    </section>
  );
}
