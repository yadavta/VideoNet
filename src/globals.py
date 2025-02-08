"""
Global constants used by various files. 
Everything that a developer must change to run this codebase on their machine should be stored here.
"""
from pathlib import Path

# you will need to CHANGE these
# the following must end with '/'
MODELS_DIR = "/gscratch/raivn/tanush/models/"
CREDENTIALS_DIR = "/gscratch/raivn/tanush/credentials/"

# you can change these if you wish, but there is no need to
REPO_DIR = Path(__file__).parent.parent
DATA_DIR = REPO_DIR / 'data'
ORIGINALS_DIR, CLIPS_DIR = DATA_DIR / 'originals', DATA_DIR / 'clips'

# these files should live inside `CREDENTIALS_DIR`
GCLOUD_API_KEY_FILENAME = "google_genai.txt"