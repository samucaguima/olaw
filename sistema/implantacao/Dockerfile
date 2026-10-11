# Imagem do aplicativo (contexto de construção: diretório sistema/).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml ./
COPY sgj ./sgj
RUN pip install ".[web]" && useradd --system --uid 10001 --no-create-home sgj && rm -rf /app/sgj

USER sgj
ENV SGJ_HOST=0.0.0.0 SGJ_PORTA=8000
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=8)"
CMD ["python", "-m", "sgj.caixa"]
