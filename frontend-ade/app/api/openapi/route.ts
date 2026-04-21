import { readFile } from "node:fs/promises";
import path from "node:path";

import { NextRequest, NextResponse } from "next/server";

type Locale = "en" | "zh";

function resolveLocale(value: string | null): Locale {
  return value === "zh" ? "zh" : "en";
}

async function readSpecForLocale(locale: Locale): Promise<string> {
  const openapiDir = path.join(process.cwd(), "public", "openapi");
  const englishPath = path.join(openapiDir, "agent-platform-openapi.json");
  const chinesePath = path.join(openapiDir, "agent-platform-openapi-zh.json");

  if (locale === "zh") {
    try {
      return await readFile(chinesePath, "utf-8");
    } catch {
      // Fallback to English if Chinese artifact is not committed yet.
    }
  }

  return readFile(englishPath, "utf-8");
}

export async function GET(request: NextRequest) {
  const locale = resolveLocale(request.nextUrl.searchParams.get("locale"));

  try {
    const payload = await readSpecForLocale(locale);

    return new NextResponse(payload, {
      status: 200,
      headers: {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "public, max-age=120",
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);

    return NextResponse.json(
      {
        detail: "Failed to read OpenAPI artifact.",
        message,
      },
      { status: 500 },
    );
  }
}