from fastapi import FastAPI

from src.core.schemas import HealthResponseSchema

app = FastAPI()


@app.get("/health")
async def health() -> HealthResponseSchema:
    return HealthResponseSchema(status="ok")
