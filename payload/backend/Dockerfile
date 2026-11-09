FROM python:3.12-slim@sha256:876416ecde9aca2bcc90e1fb0c7a9500bbf749f5788b70f82d4c5a5c2357f8b4
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PLATFORM_STT_MODEL_CACHE_DIR=/opt/orkio/models/faster-whisper
COPY pyproject.toml uv.lock requirements.lock.txt alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY src ./src
# DIAG BUILD: separate installation, native STT import and platform app import.
# Preserve this build gate: failures must remain visible, never bypassed.
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock.txt
RUN set +e; \
    echo 'DG01_STT_CHECK_BEGIN'; \
    echo 'DG01_CGROUP_BEFORE'; \
    if [ -r /sys/fs/cgroup/memory.max ]; then cat /sys/fs/cgroup/memory.max; else echo 'memory.max unavailable'; fi; \
    if [ -r /sys/fs/cgroup/memory.events ]; then cat /sys/fs/cgroup/memory.events; else echo 'memory.events unavailable'; fi; \
    python -u -X faulthandler -c "print('DG01_PYTHON_RUNNING', flush=True); import faster_whisper; print('DIAG_FASTER_WHISPER_IMPORT_OK', flush=True)"; \
    dg01_rc=$?; \
    echo "DG01_STT_IMPORT_EXIT_CODE=${dg01_rc}"; \
    echo 'DG01_CGROUP_AFTER'; \
    if [ -r /sys/fs/cgroup/memory.events ]; then cat /sys/fs/cgroup/memory.events; fi; \
    exit "${dg01_rc}"
RUN DATABASE_URL='sqlite+pysqlite:///:memory:' \
    PLATFORM_ENVIRONMENT=test \
    PLATFORM_AUTH_MODE=test \
    python -c "import orkio_v2.main; print('DIAG_PLATFORM_APP_IMPORT_OK', flush=True)"
ARG ORKIO_STT_PREWARM_MODEL=""
RUN mkdir -p "${PLATFORM_STT_MODEL_CACHE_DIR}" \
    && if [ -n "${ORKIO_STT_PREWARM_MODEL}" ]; then \
         PLATFORM_STT_PROVIDER=faster_whisper \
         PLATFORM_STT_MODEL="${ORKIO_STT_PREWARM_MODEL}" \
         PLATFORM_STT_LOCAL_FILES_ONLY=false \
         python scripts/prewarm_stt.py; \
       else \
         echo "STT model prewarm skipped; set ORKIO_STT_PREWARM_MODEL at build time to bake a model cache."; \
       fi
RUN groupadd --system --gid 10001 orkio \
    && useradd --system --uid 10001 --gid 10001 --create-home --home-dir /home/orkio orkio \
    && mkdir -p /opt/orkio/models/faster-whisper /app/data/artifacts /app/data/tts-cache \
    && chown -R orkio:orkio /app /opt/orkio /home/orkio
ENV HOME=/home/orkio
USER orkio
EXPOSE 8080
CMD ["uvicorn","orkio_v2.main:app","--host","0.0.0.0","--port","8080"]
