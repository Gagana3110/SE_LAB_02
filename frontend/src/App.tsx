import { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Role } from "./api";
import { AuthProvider, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { BomPage } from "./pages/BomPage";
import { ImportPage } from "./pages/ImportPage";
import { ItemsPage } from "./pages/ItemsPage";
import { LoginPage } from "./pages/LoginPage";
import { MaterialSuppliersPage } from "./pages/MaterialSuppliersPage";
import { SuppliersPage } from "./pages/SuppliersPage";
import { UsersPage } from "./pages/UsersPage";
import "./styles.css";

const BUYERS: Role[] = ["administrator", "procurement_manager"];

/** Hides pages a role cannot use. The server still checks every request (DFS-SR-003). */
function Allowed({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth();
  if (user && !roles.includes(user.role)) {
    return (
      <section>
        <h1>No access</h1>
        <p>Your role does not have access to this page.</p>
      </section>
    );
  }
  return <>{children}</>;
}

function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) return <p className="loading">Loading...</p>;
  if (!user) return <LoginPage />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/products" replace />} />
        <Route path="products" element={<ItemsPage kind="products" title="Products" />} />
        <Route path="products/:id/bom" element={<BomPage />} />
        <Route path="materials" element={<ItemsPage kind="materials" title="Raw materials" />} />
        <Route
          path="materials/:id/suppliers"
          element={
            <Allowed roles={BUYERS}>
              <MaterialSuppliersPage />
            </Allowed>
          }
        />
        <Route
          path="suppliers"
          element={
            <Allowed roles={BUYERS}>
              <SuppliersPage />
            </Allowed>
          }
        />
        <Route
          path="import"
          element={
            <Allowed roles={["demand_planner"]}>
              <ImportPage />
            </Allowed>
          }
        />
        <Route
          path="users"
          element={
            <Allowed roles={["administrator"]}>
              <UsersPage />
            </Allowed>
          }
        />
        <Route path="*" element={<Navigate to="/products" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
