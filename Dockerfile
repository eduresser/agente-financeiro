FROM docker.io/library/python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8501

ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["sh", "-c", "python -m banco_agil.seed && exec streamlit run src/banco_agil/ui/streamlit_app.py --server.address=0.0.0.0 --server.port=8501 --browser.gatherUsageStats=false"]
