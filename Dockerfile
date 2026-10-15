FROM python:3.12-slim

WORKDIR /app

# Variáveis para logs em tempo real sem buffering
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Instala apenas o minimo do sistema necessario para o Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependencias Python primeiro (camada cacheada separadamente do codigo)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala Chromium com TODAS as suas dependencias de sistema (--with-deps faz o apt-get interno)
RUN playwright install chromium --with-deps

# Copia o codigo fonte e o frontend estático
COPY src/ ./src/
COPY index.html ./index.html

# Porta interna do container
EXPOSE 8000

# Ponto de entrada: Uvicorn sobe a API FastAPI e gerencia o agendador em background
CMD ["uvicorn", "controller.api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]