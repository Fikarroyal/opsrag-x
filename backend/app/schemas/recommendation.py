from __future__ import annotations

from pydantic import BaseModel


class Recommendation(BaseModel):
    order: int
    type: str = "RECOMMENDATION"
    text: str
    evidence_refs: list[str]
    sop_reference: str | None = None
    requires_human_approval: bool = True


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str | None = None
