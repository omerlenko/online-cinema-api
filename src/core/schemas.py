from pydantic import BaseModel


class HealthResponseSchema(BaseModel):
    status: str
