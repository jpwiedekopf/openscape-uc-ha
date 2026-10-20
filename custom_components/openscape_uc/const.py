"""Constants for the OpenScape UC integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "openscape_uc"
LOGGER = logging.getLogger(__package__)

CONF_TRUST_INTERNAL_CERTS: Final = "trust_internal_certs"

DEFAULT_TRUST_INTERNAL_CERTS: Final = False
DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=30)
REQUEST_TIMEOUT: Final = 15
STORAGE_VERSION: Final = 1
