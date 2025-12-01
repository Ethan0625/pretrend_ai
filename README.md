# Pretrend AI — 주식 자동매매 시스템 (Pre-Trend Value 기반)

본 프로젝트는 **Pre-Trend Value** 관점에서  
- 유효한 데이터(EOD·뉴스·정책·거시) 기반 분석  
- 테마 스코어링 + 저평가 종목 필터링  
- LLM 기반 리서치  
- EOD 기반 자동매매 신호 생성  

까지 포함하는 **종합 자동매매 시스템**을 구축하는 것을 목표로 한다.

본 Repository는 다음 기능을 포함한다.

- 🎛 **FastAPI 기반 백엔드 API**
- 🧠 **vLLM 기반 LLM 서버(Qwen/Llama 계열)**
- 📊 **데이터 파이프라인 / Airflow ETL**
- 📚 **리서치(Notebook) 기반 모델 실험**
- 🧩 **전략/신호 생성 로직**
- 📦 **Docker/K8s 기반 배포 구성(향후)**

---

## 1. 폴더 구조

```text
pretrend_ai/
├─ .gitignore
├─ .env.example
├─ README.md
├─ requirements.txt
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
│      ├─ pipeline/       # 데이터 파이프라인 (EOD, 뉴스, 거시 등)
│      │   ├─ __init__.py
│      │   └─ eod_ingest.py
│      ├─ signals/        # 신호/전략 모듈
│      ├─ llm/            # LLM 클라이언트, RAG, 프롬프트 템플릿
│      ├─ config/         # 설정/스키마 정의 
│      └─ utils/          # 공통 유틸
│
├─ backend_api/
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py
│  │  ├─ config.py
│  │  ├─ routers/
│  │  ├─ services/
│  │  └─ models/
│  └─ tests/
│
├─ tests/
│  ├─ pipeline/
│  │  └─ test_step1_eod_ingest.py
│  └─ ...
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

## 2. 개발 환경 요약

| 항목 | 값 |
|------|------|
| OS | Ubuntu Linux |
| GPU | NVIDIA RTX 4090 × 4 |
| CUDA | 11.8 (nvcc) |
| PyTorch | 2.9.0+cu128 |
| vLLM | 최신 버전 |
| Python | 3.11 (Conda) |
| 가상환경 | `pretrend-dev` |
| 외부 접속 | Tailscale 사용 |

자세한 내용은 `/docs/environment.md` 참고.

---

## 3. 실행 방법

### 3.1 Conda 환경

```bash
conda activate pretrend-dev
```

### 3.2 FastAPI 서버 실행

```bash
cd backend_api
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

확인:

```
http://127.0.0.1:8100/health
```

### 3.3 vLLM 서버 실행 (예: Qwen2-7B)

```bash
CUDA_VISIBLE_DEVICES=2 python -m vllm.entrypoints.openai.api_server   --model Qwen/Qwen2-7B-Instruct   --host 0.0.0.0   --port 8101   --tensor-parallel-size 1   --max-model-len 4096   --dtype float16
```

확인:

```bash
curl http://127.0.0.1:8101/v1/models
```

---

## 4. 환경 변수 관리

- 실제 환경 변수 파일: **`.env`(Git ignore)**
- GitHub 공개용 템플릿: **`.env.example`**

```bash
# .env.example 일부
API_PORT=8100
VLLM_BASE_URL=http://127.0.0.1:8101/v1
VLLM_MODEL_NAME=Qwen/Qwen2-7B-Instruct

DB_HOST=127.0.0.1
DB_USER=pretrend_user
DB_PASSWORD=CHANGE_ME
```

---

## 5. 문서

- 환경 구성: `/docs/environment.md`
- 개발 계획: `/docs/dev_plan.md`
- 아키텍처: `/docs/architecture.md`
- API 명세: `/docs/api_spec.md`

---

## 6. 향후 작업 로드맵

- [ ] vLLM 안정 실행 / 모델 옵션 최적화  
- [ ] Airflow DAG → EOD 파이프라인 구현  
- [ ] 전략/신호 생성 모듈 개발  
- [ ] Docker → Kubernetes 전환  
- [ ] Grafana 기반 모니터링 구축  

---

## 7. 라이선스 / 기여 가이드
(추후 업데이트)

---

#### 📌 이 프로젝트는 *실제 자동매매 시스템 구축*을 목표로 하며, 코드와 문서가 함께 발전하는 형태로 관리됩니다.
