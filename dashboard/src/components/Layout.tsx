import { NavLink, Outlet } from "react-router-dom";

export default function Layout() {
  return (
    <div className="app-shell">
      <nav className="nav">
        <span className="nav-logo">Placebo</span>
        <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          Dashboard
        </NavLink>
        <NavLink to="/experiments" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          Experiments
        </NavLink>
        <NavLink to="/workouts" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          Workouts
        </NavLink>
        <NavLink to="/backups" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          Backups
        </NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
