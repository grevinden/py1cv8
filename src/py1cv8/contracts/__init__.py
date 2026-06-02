"""Contracts package — protocols for module interactions.

All inter-module dependencies MUST go through these protocols.
Implementations explicitly satisfy a contract via structural typing.
Dependency Injection at composition root (bootstrap.py).
"""

from __future__ import annotations
