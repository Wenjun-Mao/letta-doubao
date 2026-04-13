import type { Metadata } from "next";
import "./globals.css";
import { TopNav } from "./components/top-nav";

export const metadata: Metadata = {
  title: "Agent Platform ADE",
  description: "Separate ADE frontend for Agent Platform migration",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <div className="topbar-inner">
            <div className="brand">Agent Platform ADE (Preview)</div>
            <TopNav />
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
