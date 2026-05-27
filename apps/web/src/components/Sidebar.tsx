import type { ScreenId } from "@/types/screen";

interface NavItem {
  id: ScreenId;
  label: string;
  path: string;
}

interface NavGroup {
  group: string;
  items: NavItem[];
}

const NAV: NavGroup[] = [
  {
    group: "전체",
    items: [{ id: "overview", label: "개요", path: "/api/v1/meta" }],
  },
  {
    group: "관측",
    items: [
      { id: "regime", label: "시장 국면", path: "/api/v1/regime" },
      { id: "similarity", label: "유사 시기", path: "/api/v1/similarity" },
      { id: "macro", label: "거시지표", path: "/api/v1/macro" },
      { id: "eod", label: "EOD 심볼", path: "/api/v1/eod" },
    ],
  },
  {
    group: "설명",
    items: [{ id: "explain", label: "설명", path: "/api/v1/explain" }],
  },
  {
    group: "런타임",
    items: [
      { id: "lineage", label: "데이터 흐름", path: "data/gold" },
      { id: "dags", label: "작업", path: "airflow" },
    ],
  },
  {
    group: "운영",
    items: [
      { id: "debug-history", label: "디버그 히스토리", path: "docs/operation" },
    ],
  },
];

export interface SidebarProps {
  active: ScreenId;
  onSelect?: (id: ScreenId) => void;
}

export function Sidebar({ active, onSelect }: SidebarProps) {
  return (
    <aside className="sidebar">
      {NAV.map((group) => (
        <div className="sidebar-section" key={group.group}>
          <div className="sidebar-group">{group.group}</div>
          {group.items.map((item) => (
            <button
              className={`nav-item ${item.id === active ? "active" : ""}`}
              key={item.id}
              type="button"
              onClick={() => onSelect?.(item.id)}
            >
              <span className="nav-key">{item.label}</span>
              <span className="nav-path">{item.path}</span>
            </button>
          ))}
        </div>
      ))}
    </aside>
  );
}
