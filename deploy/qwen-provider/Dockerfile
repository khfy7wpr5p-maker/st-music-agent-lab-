FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY deploy/qwen-provider/requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

COPY deploy/qwen-provider/server.py /app/server.py

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
