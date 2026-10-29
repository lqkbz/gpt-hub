# AstrBot + Node + Codex CLI
ARG ASTRBOT_IMAGE=soulter/astrbot:latest
FROM ${ASTRBOT_IMAGE}

ARG CODEX_VERSION=0.165.0
ARG NODE_MAJOR=22

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @openai/codex@${CODEX_VERSION} \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

# Codex 凭据单独存放，不与 NapCat 共享
ENV CODEX_HOME=/root/.codex
