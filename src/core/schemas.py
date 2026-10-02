from pydantic import BaseModel


class HealthResponseSchema(BaseModel):
    status: str
    database: str


class ErrorResponseSchema(BaseModel):
    detail: str
