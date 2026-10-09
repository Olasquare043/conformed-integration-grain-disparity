# Pipeline image: Python 3.12 with the exact environment locked in uv.lock.
# Both base images are pinned by digest, because a tag can be repointed upstream.

FROM ghcr.io/astral-sh/uv:0.10.8@sha256:88234bc9e09c2b2f6d176a3daf411419eb0370d450a08129257410de9cfafd2a AS uv

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

COPY --from=uv /uv /uvx /usr/local/bin/

# make runs the stages, git records the commit in the run log, libgomp1 is
# needed by LightGBM, and a fixed font keeps figures identical between runs.
RUN apt-get update \
 && apt-get install -y --no-install-recommends make git libgomp1 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory /app

# The environment lives outside /app so the bind-mounted repository (which may
# hold a host .venv built for another operating system) never replaces it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_FROZEN=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    TZ=UTC \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# Dependencies first, so editing source code does not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

CMD ["make", "help"]
