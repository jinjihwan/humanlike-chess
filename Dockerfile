FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/user/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user

WORKDIR /home/user/app
COPY requirements.txt ./requirements.txt

# Use a CPU-only PyTorch build: avoids downloading large CUDA libraries.
RUN python -m pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN python -m pip install --no-cache-dir -r requirements.txt
RUN python -m pip install --no-cache-dir git+https://github.com/CSSLab/maia3.git

USER user
COPY --chown=user:user server.py opening_book.py ./
COPY --chown=user:user static ./static

# Download the lightweight 5M model during image build.
RUN maia3-cache --model maia3-5m

EXPOSE 7860
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
