"""Absentee ballot application CSV parser for GA SoS bulk data files."""

from voter_api.lib.absentee.parser import GA_SOS_ABSENTEE_COLUMN_MAP, parse_absentee_csv_chunks

__all__ = [
    "GA_SOS_ABSENTEE_COLUMN_MAP",
    "parse_absentee_csv_chunks",
]
