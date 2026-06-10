import os
import sys

# Add root directory to sys.path to ensure correct module resolution
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Import and execute the frontend app code
import frontend.app
