import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("MODEL", "gemma-4-26b-a4b-it")

USE_DUMMY = os.getenv("USE_DUMMY", "false").lower() == "true"
USE_SPECIALISED = os.getenv("USE_SPECIALISED", "false").lower() == "true"
USE_VANILLA = os.getenv("USE_VANILLA", "false").lower() == "true"
SKIP_FILE_PLANNING = os.getenv("SKIP_FILE_PLANNING", "false").lower() == "true"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if USE_DUMMY:
    BENCH_NAME = "DummyBench"
else:
    BENCH_NAME = "RefactorBench"