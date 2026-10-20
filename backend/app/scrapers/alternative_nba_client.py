"""Deprecated shim — use ESPNNBAClient / NBAAPIClient instead."""

from .espn_nba_client import ESPNNBAClient as AlternativeNBAClient

__all__ = ["AlternativeNBAClient"]
