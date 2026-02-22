"""GoverningBodyType model — admin-extensible lookup table for body classifications.

Default types (county commission, city council, etc.) are seeded via migration.
Admins can add custom types via the API. Default types cannot be deleted.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin


class GoverningBodyType(Base, UUIDMixin):
    """Lookup table for governing body classifications.

    Attributes:
        name: Display name (e.g., "County Commission"). Unique.
        slug: URL-safe identifier (e.g., "county-commission"). Unique.
        description: Optional description of the type.
        is_default: System-provided (True) vs admin-added (False).
        created_at: When the record was created.
    """

    __tablename__ = "governing_body_types"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
