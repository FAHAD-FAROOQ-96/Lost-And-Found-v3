import sys
import os

# Ensure root directory is accessible
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import app, setup_sample_data

# SAFE execution (prevents crash)
try:
    setup_sample_data()
except Exception as e:
    print("Seeding failed:", e)

# REQUIRED
handler = app