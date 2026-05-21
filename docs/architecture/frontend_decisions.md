# Frontend Decisions

Version: 2026.05.21
Status: **Working — P31 local E2E PASS, contract promotion pending.** Promote to `frontend_contract.md` after 1-week operational stability check.
Markers: architecture, observability, phase-3

> 📝 **Lifecycle**: 본 문서는 Phase 3 대시보드 구현 진입 전 **사전 결정 SOT**다. 대시보드 로컬 E2E 검증 완료 + 운영 사용 1주 이상 안정화 후 `docs/architecture/frontend_contract.md`로 승격된다. 승격 시 본 파일은 archive 또는 contract로 git mv.

---

## 1. 목적

Phase 2 stage gate (P29) 완료 직후 시점. Phase 3 React Dashboard parent + leaf task 작성에 앞서 다음 분기점을 사전 확정해서 task 문서들이 단일 SOT를 참조하도록 한다.

배경:
- P28까지 read-only FastAPI (11 endpoint) 완성, P30 운영 재현성 baseline 확정.
- `.agent/design_sample/` 32 file로 hi-fi design system + UI kit prototype 작성 완료.
- Phase 3 task 분해 전 폴더 위치 / 차트 라이브러리 / i18n / explainability scope 결정 필요.

---

## 2. 결정 사항 (2026-05-19 확정)

### 2.1 폴더 구조 — `apps/web/`

| 항목 | 결정 |
|---|---|
| 위치 | `apps/web/` (top-level, REFACTOR_2026Q2.md §2.3 원안 유지) |
| 빌드 | Vite + React + TypeScript |
| 패키지 매니저 | npm |
| 개발/검증 기준 | Docker Compose (`web-node`) |
| 런타임 기준 | Docker Compose `web` service + nginx static serve |

**근거**:
- React/TS는 Python 패키지(`src/pretrend/`) 안에 못 들어감. top-level 위치 필수.
- `apps/web/` 컨벤션이 향후 `apps/{cli,worker}` 확장 여지.
- `.agent/design_sample/ui_kits/observability/README.md`가 이미 `apps/web/` 가정.
- host Node/npm 설치 여부에 의존하지 않도록 Docker를 frontend 표준 실행 환경으로 둔다.

**Out-of-Scope**: mobile / desktop app. 현재 web만.

**Dashboard API 인증 기준**:
- Docker `web` runtime은 브라우저 번들에 API key를 굽지 않는다.
- nginx same-origin proxy가 `PRETREND_API_KEY`를 서버 측에서 `X-API-Key`로 주입한다.
- `VITE_API_KEY`는 `web-node`/Vite dev server로 직접 개발할 때만 사용한다.

### 2.2 차트 라이브러리 — Recharts 기본 + 필요 시 Visx 추가

| 차트 | 라이브러리 |
|---|---|
| Regime timeline (line) | Recharts |
| Macro indicator timeline | Recharts |
| EOD price timeline | Recharts |
| Similarity Top-N (table 위주) | Recharts (또는 plain table) |
| ETF heatmap | **Phase 3 후반 결정** — Recharts heatmap (실험적) 또는 Visx |
| Similarity replay (custom) | **Phase 3 후반 결정** — 복잡도에 따라 Visx |

**근거**:
- design_sample의 strip / table 중심 viz는 Recharts로 70% 커버.
- ETF heatmap / similarity replay 같은 custom viz는 후반 Visx 검토.
- ECharts: bundle 크기 트레이드오프 큼. 단일 라이브러리 정책 불필요.
- D3 직접 사용: 학습/작성 비용 큼, 회피.

**Out-of-Scope**: 실시간 streaming charts (WebSocket). Phase 3 read-only 정합.

### 2.3 i18n 정책 — 한국어 UI + 영문 메타

| 영역 | 언어 |
|---|---|
| UI 라벨 / 버튼 / 페이지 제목 | 한국어 |
| Endpoint path / schema field / mono label / API 응답 컬럼명 | 영어 (원본 유지) |
| Date / number format | ko-KR locale (예: `2026-05-19`, `1,234.56`) |
| Mono font (`JetBrains Mono`) 영역 | 영어 / ASCII |

**근거**:
- 프로젝트 docs (`system_overview.md`, contract docs) 한국어 위주.
- design_sample의 영문 라벨 (`OBSERVATION`, `Historical similarity` 등)은 placeholder — Phase 3에서 한국어로 교체.
- mono / schema label은 영어 유지 (API contract 정합).

**Out-of-Scope**:
- bilingual toggle (Phase 4+ 의제).
- 영어 사용자 onboarding doc.
- 다국어 i18n library (예: `react-i18next`) — Phase 3 MVP는 단일 언어이므로 도입 보류. 텍스트는 컴포넌트 상수로 관리.

### 2.4 Explainability scope/window — Single trade_date only

| 항목 | 결정 |
|---|---|
| Phase 3 MVP scope | `(use_case, query_date)` 단일 trade_date explanation |
| Cache PK | 현재 `(use_case, query_date, model_id, prompt_version)` 변경 0 |
| Window 차원 (`rolling_30d` 등) | **Phase 4+ 의제로 보관** |
| User 임의 range + on-demand | **Phase 4+ 의제로 보관** |

**근거**:
- design_sample `ExplainPanel`은 단일 cache row 표시 구조.
- Sidebar의 Explain tab도 단수 (`/api/v1/explain`).
- window/rolling은 사용자 요구가 검증된 후 도입.

**P27 explainability schema 변경 0** — 모델 / migration / DAG / explainer 코드 모두 그대로.

---

## 3. 시각 reference

대시보드 시각 언어 / 컴포넌트 / fixture 기반:

| 자료 | 위치 | 역할 |
|---|---|---|
| Design tokens | `.agent/design_sample/colors_and_type.css` | OKLCH color / Pretendard + JetBrains Mono / radii / spacing / elevation / motion |
| Preview pages (19개) | `.agent/design_sample/preview/*.html` | 각 design primitive 단독 미리보기 |
| UI kit prototype | `.agent/design_sample/ui_kits/observability/` | 8 컴포넌트 + fixtures + index.html |
| API contract | `docs/api/observability_api_contract.md` | 11 endpoint + response schema |
| System map | `docs/architecture/system_map_2026q2.md` | 책임 매트릭스 + Track boundary |
| Boundary contract | `docs/architecture/boundary_contract.md` | 금지 dependency / "예측 금지" invariant |

→ Phase 3 첫 leaf는 `colors_and_type.css`를 `apps/web/src/styles/tokens.css`로 그대로 이전.

---

## 4. Phase 3 task 작성에 미치는 영향

Phase 3 parent + leaf 분해 시 본 결정을 반영:

1. **scaffolding leaf** — `apps/web/` Vite + React + TS 골격, design tokens 이전, Recharts 의존 추가, Docker 기반 npm 검증.
2. **layout leaf** — Topbar / Sidebar / Toolbar / main grid (design_sample 1:1 이전).
3. **screen leaves** — Regime / Similarity / Macro / EOD / Explain / Overview (각 1 endpoint 매핑, 한국어 라벨).
4. **차트 leaf** — Recharts 기본 차트 (timeline). heatmap은 후반 결정.
5. **API client leaf** — TypeScript types (fixtures.js shape → TS) + fetch wrapper + auth header.
6. **integration leaf** — docker-compose `web` 서비스 기준의 API 연결 / 로컬 E2E를 확장 검증.
7. **docs/queue/changelog leaf** — 본 문서 → contract 승격 가능 시점 평가.

---

## 5. 승격 기준 (`frontend_decisions.md` → `frontend_contract.md`)

다음 조건 모두 충족 시 승격:

- [x] Phase 3 dashboard 로컬 E2E 검증 PASS (모든 screen 200 응답, 차트 렌더 OK).
- [x] 4 결정 모두 실제 구현에서 유효 입증 (구현 중 결정 번복 0).
- [ ] design tokens (`apps/web/src/styles/tokens.css`)가 `colors_and_type.css`와 정합 + 운영 1주 이상 변경 0.
- [x] 한국어 UI 라벨이 사용자 검증 완료.
- [x] Recharts 기본 + Visx 추가 시점 명확화 (어떤 차트가 Visx인가).
- [x] Cloudflare Tunnel 외부 노출 전 (외부 노출은 contract 승격 trigger 아님 — 별도 운영 task).

### 5.1 P31 승격 평가 (2026-05-21)

**평가 결과: 미승격.**

- P31 로컬 E2E는 통과했다: frontend typecheck/build, `docker compose build web`, `pretrend-web` healthy, nginx same-origin `/api/v1/meta` smoke PASS.
- 구현 중 4개 사전 결정(`apps/web/`, Recharts 기본, 한국어 UI + 영문 메타, single trade_date explainability)은 번복되지 않았다.
- 운영 `web`은 브라우저 bundle에 API key를 굽지 않고 nginx proxy가 서버 측에서 `X-API-Key`를 주입한다.
- 미승격 사유는 단 하나다: `tokens.css` 운영 1주 이상 변경 0 조건이 아직 충족되지 않았다.
- 재평가 시점: P31 운영 1주 후. 조건 충족 시 `frontend_contract.md`로 승격한다.

승격 작업:
- `git mv docs/architecture/frontend_decisions.md docs/architecture/frontend_contract.md`.
- Status 변경: `Working` → `active contract`.
- 본 §5 승격 기준 → §"승격 이력" 1줄로 압축.
- §1 목적 → contract 관점으로 재작성 ("Phase 3 대시보드 frontend의 SOT").

---

## 6. Out-of-Scope (명시적 미결정 / 다음 단계)

- **차트 라이브러리 확장** (Visx / ECharts) 도입 시점 — Phase 3 후반 결정.
- **Theme switching** (dark/light toggle) — Phase 3 MVP는 paper (light) 단일.
- **bilingual i18n** — Phase 4+ 의제.
- **WebSocket / SSE streaming** — read-only Phase 2/3 정합 위해 도입 안 함.
- **Auth UI** — Phase 3 로컬은 single user, API key는 환경 변수. 외부 노출 시점에 재검토.
- **Cloudflare Tunnel 외부 노출 사용자 정책** — 별도 운영 task.

---

## 7. 변경 이력

- 2026-05-19: 초안 작성 (Phase 3 사전 결정 SOT). 4 결정 채택 — `apps/web/` / Recharts 기본 / 한국어 UI + 영문 메타 / single trade_date explainability. 승격 lifecycle 명시.
- 2026-05-21: P31 local E2E 평가. 구현 결정 4개는 유효하나 운영 1주 안정화 조건 미충족으로 contract 승격 보류.
