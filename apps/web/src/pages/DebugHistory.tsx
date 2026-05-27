import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import type { PillVariant } from "@/components/primitives/Pill";
import { INCIDENTS } from "@/data/incidents";
import type { IncidentSummary } from "@/data/incidents";

function severityVariant(s: IncidentSummary["severity"]): PillVariant {
  switch (s) {
    case "Critical": return "danger";
    case "High":     return "warn";
    case "Medium":   return "info";
    case "Low":      return "unknown";
  }
}

function statusVariant(s: IncidentSummary["status"]): PillVariant {
  switch (s) {
    case "Resolved":     return "gold";
    case "Monitoring":   return "warn";
    case "Deferred":     return "unknown";
    default:             return "info";
  }
}

export function DebugHistory() {
  return (
    <div className="panel">
      <PanelHead title="디버그 히스토리" sub="운영 incident 추적" />
      <table className="tbl">
        <thead>
          <tr>
            <th>ID</th>
            <th>날짜</th>
            <th>영역</th>
            <th>심각도</th>
            <th>상태</th>
            <th>증상</th>
            <th>근본 원인</th>
            <th>가드</th>
            <th>상세</th>
          </tr>
        </thead>
        <tbody>
          {INCIDENTS.map((inc) => (
            <tr key={inc.id}>
              <td>{inc.id}</td>
              <td>{inc.date}</td>
              <td>{inc.area}</td>
              <td><Pill variant={severityVariant(inc.severity)}>{inc.severity}</Pill></td>
              <td><Pill variant={statusVariant(inc.status)}>{inc.status}</Pill></td>
              <td>{inc.symptom}</td>
              <td>{inc.rootCause}</td>
              <td>{inc.guard}</td>
              <td>
                {inc.detailPath
                  ? <a href={inc.detailPath} target="_blank" rel="noreferrer">상세</a>
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
