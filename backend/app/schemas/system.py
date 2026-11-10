from app.schemas.base import ApiSchema


class HealthResponse(ApiSchema):
    status: str
    service: str
    environment: str


class ReadinessCheck(ApiSchema):
    name: str
    ok: bool
    detail: str | None = None


class ReadinessResponse(ApiSchema):
    status: str
    checks: list[ReadinessCheck]
