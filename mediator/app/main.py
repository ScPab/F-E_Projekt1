"""
DataBridge Mediator – FastAPI-Grundgerüst.

Der Mediator ist der zentrale Einstiegspunkt der Mediator-Wrapper-Architektur:
Er nimmt Anfragen entgegen und delegiert sie (in späteren Ausbaustufen) an die
passenden Wrapper-Module (z. B. wrappers/gdc) für die eigentliche Datenbeschaffung.

Hinweis: Dies ist bewusst noch ohne Business-Logik. Die Integrations- und
Transformationslogik (z. B. Aufruf des GDC-Wrappers, Export nach anndata/.h5ad,
Anbindung an graph-db) folgt in späteren Schritten.
"""

from fastapi import FastAPI

app = FastAPI(
    title="DataBridge Mediator",
    description="Zentraler Mediator-Service der DataBridge-Architektur (Mediator-Wrapper-Muster).",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Einfacher Health-Check, damit Orchestrierung (z. B. Docker Compose) den Service prüfen kann."""
    return {"status": "ok"}
