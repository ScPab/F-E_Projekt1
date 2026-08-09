# Mediator-Service – Basis-Image mit Mamba für schnelles Conda-Dependency-Management
# (wissenschaftliche Pakete wie anndata/scanpy profitieren von conda-forge/bioconda).
FROM condaforge/mambaforge:latest

WORKDIR /app

# Build-Context ist das Repo-Root (siehe docker-compose.yml), damit sowohl der
# Mediator-Code als auch das lokale Wrapper-Package (/wrappers) verfügbar sind.
COPY mediator/environment.yml /app/environment.yml
COPY wrappers /wrappers

# Environment aus environment.yml erzeugen. Name laut environment.yml: databridge-mediator.
RUN mamba env create -f /app/environment.yml && mamba clean --all --yes

COPY mediator/app /app/app

# Aktiviert das Conda-Environment für nachfolgende RUN/CMD-Befehle.
SHELL ["mamba", "run", "-n", "databridge-mediator", "/bin/bash", "-c"]

EXPOSE 8000

# Health-Check nutzt den /health-Endpoint des FastAPI-Grundgerüsts.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD mamba run -n databridge-mediator python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["mamba", "run", "--no-capture-output", "-n", "databridge-mediator", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
