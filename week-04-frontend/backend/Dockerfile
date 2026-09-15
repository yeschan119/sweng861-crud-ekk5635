# The backend image.
#
# Two stages. The first installs the dependencies, the second runs the service
# and carries none of the machinery that installed them: no pip cache, no
# wheels, no build tools. That is a smaller image, and it is a smaller surface
# - a toolchain in a running container is what turns a foothold into a build
# environment for an attacker.
#
# The interpreter is pinned, and pinned to a version that was measured rather
# than assumed. The repository had no Python version anywhere - not in
# requirements.txt, not in a workflow, not here - so "which Python" was decided
# by whatever each machine happened to have. The suite was run inside
# python:3.12-slim, 3.13-slim and 3.14-slim before this line was written and
# passes on all three; 3.14 is chosen because it is what the service is
# developed and tested against on the host, so the container and the laptop
# cannot drift apart.
#
# AI use: drafted with Claude and verified by building and running the stack.

# ---------------------------------------------------------------------------
# Stage 1 - dependencies
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

# A virtualenv rather than the system site-packages, so the second stage can
# take the dependencies as one directory and leave everything else behind.
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# Copied on its own, before the source. Docker caches a layer until its inputs
# change, so editing a handler does not reinstall SQLAlchemy - which is the
# difference between a five-second rebuild and a two-minute one during the
# work this image exists to support.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 - runtime
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

# Unbuffered so log lines appear when they are written rather than when the
# buffer fills. A container's stdout is its log, and a crash would otherwise
# take the last few lines of explanation with it.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# A non-root user, created before anything is copied in. The default is root,
# and a process that never needs to write outside its own directory has no
# reason to run as the account that can write anywhere - including to the
# mounted volumes of anything else that shares this daemon.
RUN useradd --create-home --uid 10001 app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
# Ownership is set during the copy rather than by a later chown: a chown on a
# copied tree writes a second full copy of it into the next layer.
# The backend is the image; the frontend is the one page it serves at /. They
# are copied separately, to the layout main.py already resolves - it looks for
# ../frontend/index.html relative to itself, which from /app is /frontend. The
# build context is week-03-backend/ rather than backend/ for this reason alone:
# COPY cannot reach outside its context, so with the context one level down the
# page was simply absent and every request for / answered 500 - in the
# container only, since running uvicorn from the source tree finds the file.
COPY --chown=app:app backend/ /app/
COPY --chown=app:app frontend/ /frontend/

USER app

EXPOSE 8000

# The same liveness probe the assignment's own health endpoint serves, so the
# orchestrator's idea of "up" is the application's. urllib rather than curl:
# the slim image ships no curl, and installing one to ask a local question
# would add a binary to the runtime stage this file exists to keep thin.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# No migration runs here. The application stopped creating its own schema in
# #23, for the reason that a service which alters tables as it boots cannot be
# started twice safely - and an entrypoint that migrated would put that back,
# one layer down. Compose runs the migration once, in its own service, before
# this one starts.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
