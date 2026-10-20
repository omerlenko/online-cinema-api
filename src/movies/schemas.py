from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class GenreCreateSchema(BaseModel):
    name: Name


class GenreReadSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)
