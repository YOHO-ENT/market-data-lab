import {
  Activity,
  BarChart3,
  Clock3,
  Database,
  LineChart,
  ListFilter,
  Menu,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink } from "react-router-dom";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="app-shell">
      <button
        className="mobile-menu-button"
        type="button"
        aria-label="Toggle navigation"
        onClick={() => setMobileOpen((open) => !open)}
      >
        {mobileOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {mobileOpen && (
        <button
          className="mobile-backdrop"
          type="button"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside className={`sidebar ${mobileOpen ? "is-open" : ""}`}>
        <div className="brand-block">
          <div className="brand-mark">
            <LineChart size={22} />
          </div>
          <div>
            <div className="brand-title">Market Data Lab</div>
            <div className="brand-subtitle">Local price intelligence</div>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Primary navigation">
          <NavLink
            to="/market"
            className={({ isActive }) => `nav-item ${isActive ? "is-active" : ""}`}
            onClick={() => setMobileOpen(false)}
          >
            <BarChart3 size={20} />
            <span>Market Matrix</span>
          </NavLink>
          <NavLink
            to="/screen"
            className={({ isActive }) => `nav-item ${isActive ? "is-active" : ""}`}
            onClick={() => setMobileOpen(false)}
          >
            <ListFilter size={20} />
            <span>Screener</span>
          </NavLink>
          <NavLink
            to="/universes"
            className={({ isActive }) => `nav-item ${isActive ? "is-active" : ""}`}
            onClick={() => setMobileOpen(false)}
          >
            <Users size={20} />
            <span>Universes</span>
          </NavLink>
          <NavLink
            to="/runs"
            className={({ isActive }) => `nav-item ${isActive ? "is-active" : ""}`}
            onClick={() => setMobileOpen(false)}
          >
            <Clock3 size={20} />
            <span>Runs</span>
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <div className="ridge" aria-hidden="true" />
          <div className="footer-item">
            <Database size={18} />
            <span>Parquet cache</span>
          </div>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div>
            <div className="topbar-title">Market Data Lab</div>
            <div className="topbar-subtitle">Technical snapshots and chart-ready local data</div>
          </div>
          <div className="topbar-status">
            <span className="status-dot" />
            <Activity size={16} />
            <span>Read only</span>
          </div>
        </header>
        <main className="content-frame">{children}</main>
      </div>
    </div>
  );
}
