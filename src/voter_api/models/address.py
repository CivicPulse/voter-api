"""Address model — canonical address store with parsed components and normalized string."""

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, TimestampMixin, UUIDMixin


class Address(Base, UUIDMixin, TimestampMixin):
    """Canonical address record with USPS-normalized form and parsed components."""

    __tablename__ = "addresses"

    normalized_address: Mapped[str] = mapped_column(Text, nullable=False)
    street_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pre_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    street_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    street_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    post_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    apt_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zipcode: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Relationships
    geocoder_cache_entries = relationship("GeocoderCache", back_populates="address", lazy="raise")
    voters = relationship("Voter", back_populates="residence_address", lazy="raise")

    __table_args__ = (
        UniqueConstraint("normalized_address", name="uq_address_normalized"),
        Index(
            "ix_addresses_normalized_prefix",
            "normalized_address",
            postgresql_ops={"normalized_address": "text_pattern_ops"},
        ),
        Index("ix_addresses_zipcode", "zipcode"),
        Index("ix_addresses_city_state", "city", "state"),
    )
