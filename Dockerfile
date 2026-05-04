FROM python:3.12-slim

WORKDIR /app

# Instala apenas o minimo do sistema necessario para o Playwright
# --with-deps no playwright install cuida do resto automaticamente
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependencias Python primeiro (camada cacheada separadamente do codigo)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala Chromium com TODAS as suas dependencias de sistema (--with-deps faz o apt-get interno)
RUN playwright install chromium --with-deps

# Copia o codigo fonte
COPY src/ ./src/

# Ponto de entrada: main.py esta em src/
CMD ["python", "src/main.py"]