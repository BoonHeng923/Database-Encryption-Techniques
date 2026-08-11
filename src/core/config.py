"""Central configuration, read from environment variables (populated via .env / docker-compose)."""
import base64
import os

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return val


POSTGRES_HOST = _env("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(_env("POSTGRES_PORT", "5432"))
POSTGRES_DB = _env("POSTGRES_DB", "encbench")
POSTGRES_USER = _env("POSTGRES_USER", "encbench_user")
POSTGRES_PASSWORD = _env("POSTGRES_PASSWORD", "encbench_pass")

MONGO_URI = _env(
    "MONGO_URI",
    "mongodb://encbench_user:encbench_pass@localhost:27017/encbench?authSource=encbench",
)
MONGO_DB = "encbench"

PAD_BUCKET_SIZE = int(_env("PAD_BUCKET_SIZE", "50"))

_key_b64 = os.environ.get("ENC_MASTER_KEY_B64", "")
if _key_b64:
    ENC_MASTER_KEY = base64.b64decode(_key_b64)
else:
    # Deterministic fallback so a fresh clone runs out of the box for experimentation.
    # For results going into the report, set ENC_MASTER_KEY_B64 explicitly (see README).
    ENC_MASTER_KEY = b"encbench-demo-key-DO-NOT-USE-32B"[:32]

if len(ENC_MASTER_KEY) != 32:
    raise RuntimeError("ENC_MASTER_KEY_B64 must decode to exactly 32 bytes")

DATA_RAW_DIR = os.path.join("data", "raw")
DATA_PROCESSED_DIR = os.path.join("data", "processed")
RESULTS_DIR = "results"

RAW_EXCEL_PATH = os.path.join(DATA_RAW_DIR, "adult_inpatient_patient_portal_data.xlsx")

# Plan B.5: 1k / 10k / full-dataset sub-sampling scale points. "Full" is resolved
# dynamically at runtime (src.core.dataset.full_dataset_size()) since it depends on
# whichever raw file is actually present, not hardcoded here.
SMALL_SCALE_POINTS = [1_000, 10_000]
DEFAULT_APPROACHES = ["A", "B", "C"]
DEFAULT_ENGINES = ["postgres", "mongo"]
DEFAULT_REPEATS = 3
DEFAULT_N_QUERIES = 5_000
WORKLOAD_SEED = 42
# Chosen per the B.5.1 sanity check (src/analysis/dataset_profile.py): 297 distinct
# values, top-10 share 59%, max/min frequency ratio ~99,000x — categorical, skewed,
# and non-trivial without being near-unique.
SENSITIVE_FIELD = "specific_diagnostic_test"
