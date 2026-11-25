"""Repository root for tests, so they run in any checkout (CI runner, dev container, laptop)."""
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
