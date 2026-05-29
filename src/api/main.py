"""
CFP Audit Intelligence — API REST (FastAPI).

Expone los datos del catálogo CFP, resoluciones, entidades,
comparaciones INIDEP y alertas a través de endpoints REST con
documentación OpenAPI auto-generada.

Arrancar con:
    uvicorn src.api.main:app --reload --port 8000
o:
    python -m src.api.main
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from src.api.routers import actas, entidades, alertas, inidep, analysis

app = FastAPI(
    title="CFP Audit Intelligence API",
    description=(
        "API REST para acceder a los datos procesados de las actas públicas "
        "del Consejo Federal Pesquero de Argentina (1998–presente). "
        "Incluye resoluciones, entidades pesqueras, comparaciones CFP vs. INIDEP "
        "y el sistema de alertas de sostenibilidad."
    ),
    version="0.3.0",
    contact={
        "name": "CFP Audit Intelligence",
        "url": "https://github.com/arielgiamportone/cfp-audit-intelligence",
    },
    license_info={"name": "MIT"},
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

app.include_router(actas.router)
app.include_router(entidades.router)
app.include_router(alertas.router)
app.include_router(inidep.router)
app.include_router(analysis.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["sistema"], summary="Health check")
def health():
    return {"status": "ok", "version": "0.3.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
