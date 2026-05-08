"""Thin forwarder kept for backwards compatibility with existing imports.

The real domain-split registry lives under `route_registry/`. This file re-exports
`register_routes` so any caller doing `from route_registration import register_routes`
still works.
"""
from route_registry import register_routes

__all__ = ["register_routes"]
