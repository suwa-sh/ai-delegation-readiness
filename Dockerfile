FROM python:3.14-slim

# The pinned overlay engine version, passed by the release workflow (parsed from
# pyproject). Recorded as an OCI label; the authoritative record is the baked-in
# pip freeze and `aidr --version`. Defaults to "unknown" for manual builds.
ARG OVERLAY_ENGINE_VERSION=unknown
# App version, passed by the release workflow (derived from the git tag) so the
# label never drifts from the released version. Defaults to "unknown" for
# manual builds.
ARG APP_VERSION=unknown

LABEL org.opencontainers.image.title="ai-delegation-readiness" \
      org.opencontainers.image.description="Diagnose whether a business judgment is ready to be delegated to an AI agent." \
      org.opencontainers.image.source="https://github.com/suwa-sh/ai-delegation-readiness" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${APP_VERSION}" \
      sh.suwa.overlay-engine.version="${OVERLAY_ENGINE_VERSION}"

WORKDIR /app
COPY . /app

# Editable install: the CLI resolves the bundled definitions/ relative to the
# repo root (Path(__file__).parents[2]), so the source tree must stay in place.
# pip pulls the exact-pinned overlay-scoring-skeleton from PyPI (which therefore
# must be published first). The baked-in freeze is the authoritative record of
# which engine version this image contains.
RUN pip install --no-cache-dir -e . \
    && pip freeze > /app/requirements.frozen.txt \
    && aidr --version

ENTRYPOINT ["aidr"]
CMD ["--help"]
