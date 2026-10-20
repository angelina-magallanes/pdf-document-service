from fastapi import FastAPI

app = FastAPI(title="Servicio de persistencia de documentos")

@app.get("/health")
@app.get("/health/live")
def health_live():
    return {"status": "ok"}