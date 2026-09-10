"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Compass, LineChart, TrendingUp, Zap, Briefcase, LogOut } from "lucide-react";
import { clearToken } from "./api-client";
import RequireAuth from "./require-auth";

const NAV_ITEMS = [
  { href: "/overview", label: "Overview", icon: Compass, match: (path: string) => path === "/overview" },
  { href: "/", label: "Instruments", icon: LineChart, match: (path: string) => path === "/" || path.startsWith("/instruments") },
  { href: "/strategies", label: "Strategies", icon: TrendingUp, match: (path: string) => path.startsWith("/strategies") },
  { href: "/actionables", label: "Actionables", icon: Zap, match: (path: string) => path.startsWith("/actionables") },
  { href: "/portfolio", label: "Portfolio", icon: Briefcase, match: (path: string) => path.startsWith("/portfolio") },
];

function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="mark" />
        <div>
          <div className="sidebar-brand-name">AEGIS Cockpit</div>
          <div className="sidebar-brand-sub">Decision support</div>
        </div>
      </div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = item.match(pathname ?? "");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`sidebar-nav-item ${active ? "active" : ""}`}
            >
              <Icon size={18} strokeWidth={2} />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <button
        className="sidebar-signout"
        onClick={() => {
          clearToken();
          router.replace("/login");
        }}
      >
        <LogOut size={16} strokeWidth={2} />
        Sign out
      </button>
    </aside>
  );
}

export default function CockpitShell({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <div className="shell">
        <Sidebar />
        <main className="content">{children}</main>
      </div>
    </RequireAuth>
  );
}
