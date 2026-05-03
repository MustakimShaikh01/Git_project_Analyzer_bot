import sys
import os

# Add backend/ to sys.path so `app` is importable without installing as a package
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
