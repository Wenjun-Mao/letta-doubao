"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fetchCapabilities, fetchMigrationStatus, listAgents, listTestRuns } from "../lib/api";

const DOCS_HREF = process.env.NEXT_PUBLIC_MINTLIFY_DOCS_URL || "/api-docs";

const MODULES = [
  {
    title: "Agent Studio",
    description: "Runtime chat, prompt and persona editing, tool management, execution trace, and persistent state inspection.",
    href: "/agent-studio",
  },
  {
    title: "Test Center",
    description: "Create and monitor backend orchestrated checks and runners, including run artifacts.",
    href: "/test-center",
  },
  {
    title: "API Docs",
    description: "OpenAPI-backed Mintlify docs for external consumers and internal operator reference.",
    href: DOCS_HREF,
  },
];

function isExternalLink(href: string): boolean {
  return /^https?:\/\//i.test(href);
}

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [agentCount, setAgentCount] = useState(0);
  const [runCount, setRunCount] = useState(0);
  const [migrationMode, setMigrationMode] = useState("unknown");
  const [platformEnabled, setPlatformEnabled] = useState(false);
  const [legacyEnabled, setLegacyEnabled] = useState(false);
  const [missingCapabilities, setMissingCapabilities] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const [migration, capabilities, agents, runs] = await Promise.all([
          fetchMigrationStatus(),
          fetchCapabilities(),
          listAgents(200),
          listTestRuns(),
        ]);

        if (cancelled) {
          return;
        }

        setMigrationMode(migration.migration_mode);
        setPlatformEnabled(Boolean(migration.platform_api_enabled));
        setLegacyEnabled(Boolean(migration.legacy_api_enabled));
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
      return "platform-disabled";
    }
    if (missingCapabilities.length > 0) {
      return "degraded";
    }
    return "ready";
  }, [missingCapabilities.length, platformEnabled]);

  return (
    <section>
      <div className="kicker">ADE Preview</div>
      <h1 className="section-title">Agent Development Environment</h1>
      <p className="muted" style={{ maxWidth: 760 }}>
        This frontend runs in parallel with fallback dev_ui and validates ADE workflows before migration cutover.
      </p>

      <div className="card-grid" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>Backend Health</h3>
          <p className="muted">{loading ? "Checking..." : `Status: ${healthLabel}`}</p>
          <ul className="list">
            <li>Migration mode: {migrationMode}</li>
            <li>Platform API enabled: {platformEnabled ? "yes" : "no"}</li>
            <li>Legacy API enabled: {legacyEnabled ? "yes" : "no"}</li>
          </ul>
        </div>

        <div className="card">
          <h3>Operational Snapshot</h3>
          <ul className="list">
            <li>Known agents: {agentCount}</li>
            <li>Observed test runs: {runCount}</li>
            <li>Missing required capabilities: {missingCapabilities.length}</li>
          </ul>
        </div>

        <div className="card">
          <h3>Cutover Gate</h3>
          <p className="muted">Backend E2E green plus ADE smoke suite green.</p>
          <p className="muted" style={{ marginTop: 8 }}>
            Keep fallback frontend active through migration window.
          </p>
        </div>
      </div>

      {error ? (
        <div className="card" style={{ marginTop: 14, borderColor: "#fecaca" }}>
          <h3>Dashboard Error</h3>
          <p className="muted">{error}</p>
        </div>
      ) : null}

      <div className="card-grid" style={{ marginTop: 18 }}>
        {MODULES.map((module) => {
          const content = (
            <>
              <h3>{module.title}</h3>
              <p>{module.description}</p>
              <p className="dashboard-module-hint">Open module</p>
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
