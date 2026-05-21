import { PanelHead } from "@/components/primitives/PanelHead";
import { Pill } from "@/components/primitives/Pill";
import { DAGS_FIXTURE } from "@/fixtures/dags";

import { Disclaimer, StatusPill } from "./_shared";

export function Dags() {
  return (
    <>
      <div className="panel">
        <PanelHead title="Airflow DAGs" sub="docker compose --profile airflow" right={<Pill variant="info">FIXTURE</Pill>} />
        <table className="tbl">
          <thead>
            <tr>
              <th>dag</th>
              <th>schedule (KST)</th>
              <th>last_run</th>
              <th>state</th>
              <th>track</th>
            </tr>
          </thead>
          <tbody>
            {DAGS_FIXTURE.map((row) => (
              <tr key={row.dag}>
                <td>{row.dag}</td>
                <td>{row.schedule}</td>
                <td>{row.lastRun}</td>
                <td><StatusPill state={row.state} /></td>
                <td>{row.track}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Disclaimer>
        본 화면은 fixture 데이터입니다. 실제 Airflow 상태와 차이가 있을 수 있으며, 운영 확인은 Airflow webserver와 `docker compose ps`를 기준으로 합니다.
      </Disclaimer>
    </>
  );
}
