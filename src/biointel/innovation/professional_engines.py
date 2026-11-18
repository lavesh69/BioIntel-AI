from __future__ import annotations

"""Compatibility facade for Step 100 professional innovation capabilities.

The implementation is split by domain to keep modules maintainable while
preserving the public import path used by pages and tests.
"""

from .professional.common import *
from .professional.genomics import *
from .professional.design import *
from .professional.knowledge import *
from .professional.workflow import *
