# 📄 개발 환경 구성 문서 (Environment Setup Guide)

**Project:** Pre-Trend Value 기반 자동매매 AI 시스템\
**Document:** Data Requirements\
**Version:** 2026.01.14\
**Purpose:** 개발·운영 환경을 표준화\

본 문서는 Pre-Trend Value 기반 자동매매 시스템의  
**개발·운영 환경을 표준화하기 위한 구성 가이드**이다.

---

# 1. 시스템 사양

| 항목           | 내용               |
|---------------|--------------------|
| OS            | Ubuntu Linux       |
| CPU           | AMD Threadripper PRO |
| RAM           | 128GB              |
| GPU           | RTX 4090 × 4       |
| CUDA (nvcc)   | 11.8               |
| PyTorch CUDA  | 12.8               |
| Python        | 3.11               |
| Conda env     | `pretrend-dev`     |

현재 머신 PyTorch 결과:

| Key                    | Value            |
|------------------------|------------------|
| `torch.__version__`    | 2.9.0+cu128      |
| `torch.version.cuda`   | 12.8             |
| `torch.cuda.is_available` | True         |
| `device_count`         | 4 (RTX 4090 × 4) |

---

# 2. 폴더 구조

```text
pretrend_ai/
├─ README.md
├─ requirements.txt
├─ .env.example
│
├─ docs/
│  ├─ dev_plan.md
│  ├─ environment.md
│  ├─ architecture.md
│  ├─ api_spec.md
│  └─ changelog.md
│
├─ src/
│  └─ pretrend/
│      ├─ pipeline/
│      ├─ signals/
│      ├─ llm/
│      ├─ config/
│      └─ utils/
│
├─ backend_api/
│  ├─ app/
│  └─ tests/
│
├─ tests/
│  └─ pipeline/
│
├─ deploy/
│  ├─ docker/
│  ├─ compose/
│  └─ k8s/
│
└─ .github/
   └─ workflows/
      └─ ci.yml
```

---

# 3. Conda 환경 구성

```bash
conda create -n pretrend-dev python=3.11 -y
conda activate pretrend-dev
```

---

# 4. 의존성 설치

```bash
pip install "fastapi[standard]"
pip install uvicorn[standard]
pip install "transformers[torch]" safetensors accelerate
pip install vllm
```

---

# 5. GPU / PyTorch 확인

```bash
python - << 'EOF'
import torch
print("torch.__version__      :", torch.__version__)
print("torch.version.cuda     :", torch.version.cuda)
print("torch.cuda.is_available:", torch.cuda.is_available())
print("device count           :", torch.cuda.device_count())
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        print(i, torch.cuda.get_device_name(i))
EOF
```

**현재 머신 결과**

| Key | Value |
|-----|-------|
| torch.__version__ | 2.9.0+cu128 |
| torch.version.cuda | 12.8 |
| torch.cuda.is_available | True |
| device_count | 4 (4090 × 4) |

---

# 6. FastAPI 서버 구성

`backend_api/app/main.py`

```python
from fastapi import FastAPI
from .config import get_settings

settings = get_settings()
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
```

실행:

```bash
uvicorn app.main:app --host 0.0.0.0 --port {YOUR_PORT}
```

---
# 7. Airflow 개발 환경 (Data Pipeline)

## 7.1 역할 및 범위
- 담당 역할:
  - Macro 파이프라인 실행 (`macro_pipeline_dag`)
  - EOD 파이프라인 실행 (향후 추가)
  - 실행 누락 대비 롤링 재처리 트리거
- 담당하지 않는 영역:
  - 전략 로직 실행
  - 실시간 트레이딩
  - LLM 추론

※ Airflow는 **데이터 생성/정합성 확보 전용**으로 사용한다.

---

## 7.2 사용 중인 DAG

| DAG ID | 설명 |
|------|----|
| `macro_pipeline_dag` | Macro Bronze → Silver 파이프라인 (매일 트리거 + 롤링 재처리) |
| `(향후)` `eod_pipeline_dag` | EOD Bronze → Silver 파이프라인 |

### Macro DAG 운영 정책 요약
- 스케줄: 매일 09:00 KST
- 실행 정책:
  - DAG는 매일 트리거되지만, 실행 누락 가능성을 전제로 설계됨
  - 각 실행 시 **직전월 1일 ~ 전일** 구간을 롤링 재처리
- 멱등성:
  - Silver Layer는 year/month 파티션 overwrite 전략 사용

---

## 7.3 실행 방식 (개발 환경 기준)

### 권장 방식
- **Docker Compose 기반 Airflow 실행**
- 로컬 개발 시 Python 가상환경 + `airflow standalone` 사용 가능

### (예시) 로컬 개발 실행
```bash
airflow standalone
```
- Web UI: http://localhost:8080
- Scheduler / Webserver 자동 실행
- 초기 계정 정보는 콘솔 출력 참고
    - 운영 환경에서는 Docker Compose 또는 Kubernetes 배포를 권장한다.

---

## 7.4 데이터 볼륨 및 경로 기준
- 현재 구현 단계에서는 파일 시스템 기반 스토리지를 사용한다.
    - 데이터 루트: data/

---

## Agent-assisted development (Codex)
- 모든 작업은 `AGENTS.md` 운영 규칙을 따른다: 작은 diff, 멱등성 보존, 공개 API 변경 지양, 검증 명령 제시.
- 브랜치는 `codex/*` 형태로 분리해 수행하고, 한 PR에는 하나의 작업만 담는다.
- 변경 전 짧은 계획을 작성하고, 변경 후에는 실행 가능한 검증 명령(예: `pytest -q`)을 함께 제공한다.
    - 주요 볼륨:
        - data/bronze/ : Raw / 정규화 데이터
        - data/silver/ : Feature 데이터
        - data/meta/ : Job 실행 메타 로그
- Airflow 실행 시:
    - DAG 코드에서 참조하는 데이터 경로는 프로젝트 루트 기준 상대 경로를 사용한다.
    - Docker 환경에서는 위 디렉토리를 volume mount 해야 한다.

※ 이 구조는 향후 DB 기반 스토리지로 대체될 수 있으며, 파일 시스템은 중간 산출물 또는 백업 용도로 유지될 예정이다.

---

## 7.5 향후 확장 방향
- Airflow → KubernetesExecutor 전환
- DAG 단위 리소스 분리
- DB 기반 Feature Store 연동
- SLA / Alerting(Grafana, Slack) 연계

---

# 8. Tailscale VPN 구성 (외부 접속용)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale status
tailscale ip
```

외부 Windows PC:

```powershell
"C:\Program Files\Tailscale	ailscale.exe" ping 100.x.x.x
curl http://100.x.x.x:{YOUR_PORT}/health
```

---

# 9. vLLM 엔진 테스트

## 9.1 최소 테스트(gpt2)

```bash
CUDA_VISIBLE_DEVICES=2 python -m vllm.entrypoints.openai.api_server   --model gpt2   --port 9000   --tensor-parallel-size 1
```

확인:

```bash
curl http://127.0.0.1:8101/v1/models
```

## 9.2 실제 모델(Qwen2-7B)

```bash
CUDA_VISIBLE_DEVICES=2 python -m vllm.entrypoints.openai.api_server   --model Qwen/Qwen2-7B-Instruct   --host 0.0.0.0   --port 9000   --tensor-parallel-size 1   --max-model-len 4096   --dtype float16
```

---

# 10. 환경 변수 관리

- 실제 파일: `.env` (Git ignore)
- 템플릿: `.env.example` (Git에 포함)

예시:

```env
API_PORT=8100
VLLM_PORT=9000
VLLM_MODEL_NAME=Qwen/Qwen2-7B-Instruct
```

### 데이터 저장소 (현재 구현 기준)

- 현재 개발 환경에서는 파일 시스템 기반 스토리지를 사용한다.
- Parquet 파일은 프로젝트 루트 하위 `data/` 디렉토리에 저장된다.
- 이 구조는 향후 DB 기반 스토리지로 대체될 수 있으며,
  파일 시스템은 중간 산출물 또는 백업 용도로 유지된다.

---

# 11. Best Practice 요약

- `.env`는 절대 커밋하지 않음  
- FastAPI는 `0.0.0.0` 바인딩  
- CUDA_VISIBLE_DEVICES는 “세션 단위 적용”  
- vLLM 모델은 작은 모델 → 7B 모델 순서로 테스트  
- 데이터/모델/로그는 Git에서 제외 (`.gitignore`)

---

# 12. 향후 확장 계획

- vLLM 안정화  
- `/llm/query` 라우팅  
- Airflow EOD 파이프라인  
- Docker → K8s 전환  
- Grafana 모니터링

---
