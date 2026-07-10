"""Shared pytest configuration for the anti-regression suite.

Puts the repository root on ``sys.path`` so ``import src.<module>`` resolves no
matter how pytest is invoked (``python -m pytest`` already prepends the CWD, but
this keeps a plain ``pytest`` working too). Also exposes ``REPO_ROOT`` for tests
that need to locate example data on disk.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
