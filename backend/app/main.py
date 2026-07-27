from fastapi import FastAPI

app = FastAPI(title="Claim AI API", version="0.0.1")


@app.get("/health")
def health() -> dict:
    """Basic liveness check. Extend later to also ping the database."""
    return {"status": "ok"}
