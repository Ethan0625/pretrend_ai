import { createBrowserRouter, Outlet, useLocation, useNavigate } from "react-router-dom";

import { Sidebar } from "./components/Sidebar";
import { Topbar } from "./components/Topbar";
import { queryClient } from "./api/queryClient";
import { useMeta } from "./api/hooks";
import type { ScreenId } from "./types/screen";
import { Dags } from "./pages/Dags";
import { Eod } from "./pages/Eod";
import { Explain } from "./pages/Explain";
import { Lineage } from "./pages/Lineage";
import { Macro } from "./pages/Macro";
import { Overview } from "./pages/Overview";
import { Regime } from "./pages/Regime";
import { Similarity } from "./pages/Similarity";

const routeByScreen: Record<ScreenId, string> = {
  overview: "/",
  regime: "/regime",
  similarity: "/similarity",
  macro: "/macro",
  eod: "/eod",
  explain: "/explain",
  lineage: "/lineage",
  dags: "/dags",
};

const labelByScreen: Record<ScreenId, { title: string; sub: string }> = {
  overview: { title: "개요", sub: "serving freshness · lineage · 관측 표면 요약" },
  regime: { title: "시장 국면", sub: "GET /api/v1/regime · cached explanation" },
  similarity: { title: "유사 시기", sub: "GET /api/v1/similarity · regime/gold views" },
  macro: { title: "거시지표", sub: "GET /api/v1/macro · timeline placeholder" },
  eod: { title: "EOD 심볼", sub: "GET /api/v1/eod · 39 ETF + 2 volatility indices" },
  explain: { title: "설명", sub: "cached observer-only reports" },
  lineage: { title: "데이터 흐름", sub: "Bronze -> Silver -> Gold -> Postgres mirror" },
  dags: { title: "작업", sub: "Airflow fixture · runtime schedule" },
};

export const router = createBrowserRouter([
  {
    element: <DashboardLayout />,
    children: [
      { path: "/", element: <Overview /> },
      { path: "/regime", element: <Regime /> },
      { path: "/similarity", element: <Similarity /> },
      { path: "/macro", element: <Macro /> },
      { path: "/eod", element: <Eod /> },
      { path: "/explain", element: <Explain /> },
      { path: "/lineage", element: <Lineage /> },
      { path: "/dags", element: <Dags /> },
    ],
  },
]);

function DashboardLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const active = screenFromPath(location.pathname);
  const meta = useMeta();
  const label = labelByScreen[active];

  return (
    <div className="app" data-screen-label={`Pretrend · ${label.title}`}>
      <Topbar
        env="local"
        alembic={meta.data?.alembic ?? "loading"}
        onRefresh={() => queryClient.invalidateQueries()}
      />
      <Sidebar active={active} onSelect={(id) => navigate(routeByScreen[id])} />
      <main className="main">
        <div className="section-head">
          <div>
            <div className="section-title">{label.title}</div>
            <div className="section-sub">{label.sub}</div>
          </div>
        </div>
        <Outlet />
      </main>
    </div>
  );
}

function screenFromPath(pathname: string): ScreenId {
  const match = (Object.entries(routeByScreen) as Array<[ScreenId, string]>).find(
    ([, path]) => path === pathname,
  );
  return match?.[0] ?? "overview";
}
