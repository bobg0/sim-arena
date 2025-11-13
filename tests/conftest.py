"""
Pytest configuration to ensure project root is on sys.path so that
`import observe...` works when running tests directly.
"""
import os
import sys

# Add the repository root (one level up from tests/) to sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
