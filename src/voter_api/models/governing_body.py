"""GoverningBody model — a local government entity that holds meetings.

Linked to a GoverningBodyType via type_id. Supports soft delete with a
partial unique constraint on (name, jurisdiction) for active records only.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from voter_api.models.governing_body_type import GoverningBodyType
    from voter_api.models.meeting import Meeting


class GoverningBody(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A local government entity (county commission, city council, etc.).

    Attributes:
        name: Official name of the governing body.
        type_id: FK to governing_body_types lookup table.
        jurisdiction: Geographic jurisdiction (free text, e.g., "Fulton County").
        description: Optional description.
        website_url: Official website URL.
    """

    __tablename__ = "governing_bodies"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("governing_body_types.id"),
        nullable=False,
    )
    jurisdiction: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    type: Mapped["GoverningBodyType"] = relationship(lazy="selectin")  # noqa: F821
    meetings: Mapped[list["Meeting"]] = relationship(  # noqa: F821
        back_populates="governing_body",
        lazy="noload",
    )

    __table_args__ = (
        Index(
            "uq_governing_body_name_jurisdiction",
            "name",
            "jurisdiction",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_governing_bodies_type_id", "type_id"),
        Index("ix_governing_bodies_jurisdiction", "jurisdiction"),
    )
