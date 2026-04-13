import Link from "next/link";

const DOCS_PATH = process.env.NEXT_PUBLIC_MINTLIFY_DOCS_URL || "/docs";

function isExternalLink(href: string): boolean {
  return /^https?:\/\//i.test(href);
}

export default function ApiDocsPage() {
  return (
    <section>
      <div className="kicker">Docs Integration</div>
      <h1 className="section-title">API Documentation</h1>
      <div className="card">
        <p>
          Mintlify documentation is configured under the repository docs folder and ingests committed OpenAPI
          artifacts generated from the backend.
        </p>
        <ul className="list">
          <li>Config: docs/docs.json</li>
          <li>Spec: docs/openapi/agent-platform-openapi.json</li>
          <li>Exporter: scripts/export_openapi.py</li>
        </ul>
        <p style={{ marginTop: 14 }}>
          {isExternalLink(DOCS_PATH) ? (
            <a href={DOCS_PATH} className="nav-link" target="_blank" rel="noreferrer">
              Open docs entry
            </a>
          ) : (
            <Link href={DOCS_PATH} className="nav-link">
              Open docs entry
            </Link>
          )}
        </p>
      </div>
    </section>
  );
}
