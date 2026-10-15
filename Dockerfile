FROM python:3.12-bookworm

ARG USER=appuser
ARG GROUP=appuser

WORKDIR /app

# Add non-root user
RUN useradd -rms /bin/bash $USER && usermod -aG users $GROUP
RUN chown -R $USER:$GROUP /app

ENV PATH="/home/${USER}/.local/bin:${PATH}"

USER $USER

COPY --chown=$USER:$GROUP src src
COPY --chown=$USER:$GROUP pyproject.toml .
RUN --mount=source=.git,target=.git,type=bind \
    python3 -m pip install .
CMD ["python-template"]
