"""Pinned production embedding model settings."""
import os
from dotenv import load_dotenv

load_dotenv()
E5_MODEL = "intfloat/multilingual-e5-base"
E5_REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", E5_MODEL)
