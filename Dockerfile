# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt requirements-dev.txt ./
RUN --mount=type=secret,id=pip_config,target=/etc/pip.conf python -m pip install --no-cache-dir -r requirements.txt
RUN groupadd -g 10001 defect && useradd -u 10001 -g defect -M defect
COPY app ./app

FROM base AS test
RUN --mount=type=secret,id=pip_config,target=/etc/pip.conf python -m pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
COPY scripts ./scripts
COPY .env.example pytest.ini ./
USER 10001:10001
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM base AS runtime
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
