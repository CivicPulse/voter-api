"""ORM model registry — import all models so Alembic autogenerate discovers them."""

from voter_api.models.election import Election, ElectionCountyResult, ElectionResult

__all__ = ["Election", "ElectionCountyResult", "ElectionResult"]
