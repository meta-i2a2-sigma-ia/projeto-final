# Dockerfile
FROM python:3.11-slim
WORKDIR /app

# deps do sistema (kaleido precisa de libs de chrome headless)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libx11-xcb1 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libxshmfence1 \
    chromium && rm -rf /var/lib/apt/lists/*
ENV CHROME_PATH=/usr/bin/chromium
ENV PYTHONUNBUFFERED=1

# requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -U plotly kaleido

# app code
COPY ./app.py ./app.py
COPY ./agents ./agents
COPY ./domain ./domain

# garante que os módulos internos sejam encontrados
ENV PYTHONPATH="/app:${PYTHONPATH}"

# variáveis (você vai sobrescrever no ECS)
ENV SUPABASE_URL=""
ENV SUPABASE_SERVICE_ROLE_KEY=""
ENV OPENAI_API_KEY=""
ENV PORT=8501

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false"]
