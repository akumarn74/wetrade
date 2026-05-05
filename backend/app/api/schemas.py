from pydantic import BaseModel


class ToggleRequest(BaseModel):
    enabled: bool


class RuntimeRequest(BaseModel):
    running: bool
