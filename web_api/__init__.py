"""HTTP API for the human Web surface."""

from web_api.app import create_app
from web_api.service import WebReadService

__all__ = ["WebReadService", "create_app"]
