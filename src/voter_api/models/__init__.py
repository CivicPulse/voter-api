"""ORM model registry — import all models so Alembic autogenerate discovers them."""

from voter_api.models.address import Address
from voter_api.models.agenda_item import AgendaItem
from voter_api.models.analysis_result import AnalysisResult
from voter_api.models.analysis_run import AnalysisRun
from voter_api.models.audit_log import AuditLog
from voter_api.models.boundary import Boundary
from voter_api.models.county_district import CountyDistrict
from voter_api.models.county_metadata import CountyMetadata
from voter_api.models.election import Election, ElectionCountyResult, ElectionResult
from voter_api.models.export_job import ExportJob
from voter_api.models.geocoded_location import GeocodedLocation
from voter_api.models.geocoder_cache import GeocoderCache
from voter_api.models.geocoding_job import GeocodingJob
from voter_api.models.governing_body import GoverningBody
from voter_api.models.governing_body_type import GoverningBodyType
from voter_api.models.import_job import ImportJob
from voter_api.models.meeting import Meeting
from voter_api.models.meeting_attachment import MeetingAttachment
from voter_api.models.meeting_video_embed import MeetingVideoEmbed
from voter_api.models.precinct_metadata import PrecinctMetadata
from voter_api.models.user import User
from voter_api.models.voter import Voter
from voter_api.models.voter_history import VoterHistory

__all__ = [
    "Address",
    "AgendaItem",
    "AnalysisResult",
    "AnalysisRun",
    "AuditLog",
    "Boundary",
    "CountyDistrict",
    "CountyMetadata",
    "Election",
    "ElectionCountyResult",
    "ElectionResult",
    "ExportJob",
    "GeocodedLocation",
    "GeocoderCache",
    "GeocodingJob",
    "GoverningBody",
    "GoverningBodyType",
    "ImportJob",
    "Meeting",
    "MeetingAttachment",
    "MeetingVideoEmbed",
    "PrecinctMetadata",
    "User",
    "Voter",
    "VoterHistory",
]
