from app.schemas.base import ApiSchema


class HealthResponse(ApiSchema):
    status: str
    service: str
    environment: str
