# Dockerfile para o módulo fiscal
FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema necessárias para kaleido/plotly (renderização headless)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libx11-xcb1 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libxshmfence1 \
    chromium && rm -rf /var/lib/apt/lists/*
ENV CHROME_PATH=/usr/bin/chromium
ENV PYTHONUNBUFFERED=1

# Dependências Python
COPY fiscal/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN pip install --no-cache-dir -U plotly kaleido

# Código da aplicação (inclui módulos compartilhados do EDA)
COPY fiscal /app/fiscal
COPY eda /app/eda

# Permite importações de pacotes locais
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Variáveis padrão (sobrescreva via docker-compose ou orchestration)
ENV SUPABASE_URL=""
ENV SUPABASE_SERVICE_ROLE_KEY=""
ENV OPENAI_API_KEY=""
ENV PORT=8502

EXPOSE 8502
CMD ["streamlit", "run", "fiscal/app.py", "--server.port=8502", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false"]
