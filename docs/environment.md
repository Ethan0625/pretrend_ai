# 📄 개발 환경 구성 문서 (Environment Setup Guide)

본 문서는 Pre-Trend Value 기반 자동매매 시스템의  
**개발·운영 환경을 표준화하기 위한 구성 가이드**이다.

---

# 1. 시스템 사양

| 항목 | 내용 |
|------|------|
| OS | Ubuntu Linux |
| CPU | AMD Threadripper PRO |
| RAM | 128GB |
| GPU | RTX 4090 × 4 |
| CUDA(nvcc) | 11.8 |
| PyTorch CUDA | 12.8 |
| Python | 3.11 |
| Conda env | `pretrend-dev` |

---

# 2. 폴더 구조

```text
pretrend-ai/
├─ backend_api/
│  ├─ app/
│  ├─ tests/
│
├─ llm_server/
├─ data_pipeline/
├─ signal_generator/
├─ research/
├─ deploy/
├─ docs/
└─ .github/
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
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

---

# 7. Tailscale VPN 구성 (외부 접속용)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale status
tailscale ip
```

외부 Windows PC:

```powershell
"C:\Program Files\Tailscale	ailscale.exe" ping 100.x.x.x
curl http://100.x.x.x:8100/health
```

---

# 8. vLLM 엔진 테스트

## 8.1 최소 테스트(gpt2)

```bash
CUDA_VISIBLE_DEVICES=2 python -m vllm.entrypoints.openai.api_server   --model gpt2   --port 8101   --tensor-parallel-size 1
```

확인:

```bash
curl http://127.0.0.1:8101/v1/models
```

## 8.2 실제 모델(Qwen2-7B)

```bash
CUDA_VISIBLE_DEVICES=2 python -m vllm.entrypoints.openai.api_server   --model Qwen/Qwen2-7B-Instruct   --host 0.0.0.0   --port 8101   --tensor-parallel-size 1   --max-model-len 4096   --dtype float16
```

---

# 9. 환경 변수 관리

- 실제 파일: `.env` (Git ignore)
- 템플릿: `.env.example` (Git에 포함)

예시:

```env
API_PORT=8100
VLLM_PORT=8101
VLLM_MODEL_NAME=Qwen/Qwen2-7B-Instruct
```

---

# 10. Best Practice 요약

- `.env`는 절대 커밋하지 않음  
- FastAPI는 `0.0.0.0` 바인딩  
- CUDA_VISIBLE_DEVICES는 “세션 단위 적용”  
- vLLM 모델은 작은 모델 → 7B 모델 순서로 테스트  
- 데이터/모델/로그는 Git에서 제외 (`.gitignore`)

---

# 11. 향후 확장 계획

- vLLM 안정화  
- `/llm/query` 라우팅  
- Airflow EOD 파이프라인  
- Docker → K8s 전환  
- Grafana 모니터링

---
