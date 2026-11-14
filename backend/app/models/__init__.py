"""SQLAlchemy model registry used by the app and Alembic."""

from app.models.api_key import UserAPIKey, UserModelPreference
from app.models.document import Document, DocumentChunk
from app.models.job import BackgroundJob
from app.models.project import ResearchProject
from app.models.report import Citation, ReportSection, ResearchReport, Source
from app.models.research import Research
from app.models.telemetry import TelemetryEvent
from app.models.usage import DailyQuotaUsage, ModelUsageDaily
from app.models.user import AuthSession, OAuthState, User

__all__ = [
    "BackgroundJob",
    "Citation",
    "DailyQuotaUsage",
    "Document",
    "DocumentChunk",
    "ModelUsageDaily",
    "ReportSection",
    "Research",
    "ResearchProject",
    "ResearchReport",
    "Source",
    "TelemetryEvent",
    "User",
    "UserAPIKey",
    "UserModelPreference",
    "AuthSession",
    "OAuthState",
]
