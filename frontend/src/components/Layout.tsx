import { NavLink, Outlet } from "react-router-dom";
import { Role } from "../api";
import { ROLE_LABELS, useAuth } from "../auth";
import { ErrorMessage } from "./Field";
import { useState } from "react";

export interface NavItem {
  to: string;
  label: string;
  roles?: Role[];
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/products", label: "Products" },
  { to: "/materials", label: "Raw materials" },
  { to: "/suppliers", label: "Suppliers", roles: ["administrator", "procurement_manager"] },
  { to: "/import", label: "Import sales", roles: ["demand_planner"] },
  { to: "/users", label: "Users", roles: ["administrator"] },
];

export function Layout() {
  const { user, logout } = useAuth();
  const [error, setError] = useState("");
  if (!user) return null;

  const signOut = () => logout().catch(() => setError("Could not log out. Please try again."));
  const visible = NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(user.role));

  return (
    <div className="shell">
      <header className="topbar">
        <strong className="brand">Demand Forecasting System</strong>
        <div className="account">
          <span>
            {user.email} ({ROLE_LABELS[user.role]})
          </span>
          <button type="button" className="secondary" onClick={signOut}>
            Log out
          </button>
        </div>
      </header>
      <nav className="menu" aria-label="Main menu">
        {visible.map((item) => (
          <NavLink key={item.to} to={item.to}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="content">
        <ErrorMessage text={error} />
        <Outlet />
      </main>
    </div>
  );
}
