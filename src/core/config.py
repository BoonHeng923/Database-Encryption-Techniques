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


MONGO_URI = _env(
    "MONGO_URI",
    "mongodb://encbench_user:encbench_pass@localhost:27017/encbench?authSource=encbench",
)
MONGO_DB = "encbench"

_key_b64 = os.environ.get("ENC_MASTER_KEY_B64", "")
if _key_b64:
    ENC_MASTER_KEY = base64.b64decode(_key_b64)
else:
    # Deterministic fallback so a fresh clone runs out of the box for experimentation.
    # For results going into the report, set ENC_MASTER_KEY_B64 explicitly (see README).
    ENC_MASTER_KEY = b"encbench-demo-key-DO-NOT-USE-32B"[:32]

if len(ENC_MASTER_KEY) != 32:
    raise RuntimeError("ENC_MASTER_KEY_B64 must decode to exactly 32 bytes")

# Separate secret for the B.4.1 real/decoy identification function (id(i)/isDecoy(i)).
# Deliberately independent of ENC_MASTER_KEY: compromising the value-encryption key must
# not also reveal which records are decoys, and vice versa.
_decoy_key_b64 = os.environ.get("DECOY_KEY_B64", "")
if _decoy_key_b64:
    DECOY_MASTER_KEY = base64.b64decode(_decoy_key_b64)
else:
    DECOY_MASTER_KEY = b"encbench-demo-decoy-key-DO-NOT-2"[:32]

if len(DECOY_MASTER_KEY) != 32:
    raise RuntimeError("DECOY_KEY_B64 must decode to exactly 32 bytes")

DATA_RAW_DIR = os.path.join("data", "raw")
DATA_PROCESSED_DIR = os.path.join("data", "processed")
RESULTS_DIR = "results"

RAW_EXCEL_PATH = os.path.join(DATA_RAW_DIR, "adult_inpatient_patient_portal_data.xlsx")

# Plan B.5 scale points, revised: 1k / 10k / 30k -- the third point was originally the
# full dataset (826,843) resolved dynamically via src.core.dataset.full_dataset_size(),
# but that made the largest run impractically slow; 30k is fixed
# here instead as a deliberate scoping choice, large enough to show scaling behaviour
# without the multi-hour runtime. `full_dataset_size()` is still available and used by the
# B.5.1 sanity-check script, which profiles the true full dataset regardless of this list.
SMALL_SCALE_POINTS = [1_000, 10_000]
SCALE_POINTS = [1_000, 10_000, 30_000]
DEFAULT_APPROACHES = ["A", "B", "C", "D"]
# The study is scoped to MongoDB. The `engine` column is still carried through
# metrics.py and generate_report.py (which filters on this list), so the pipeline stays
# engine-agnostic by design -- adding an engine means one new StorageAdapter, not a
# redesign. See SEG2102_Implementation_Details.md §7 for why the other candidate engines
# were evaluated and then descoped.
DEFAULT_ENGINES = ["mongo"]
DEFAULT_REPEATS = 3
DEFAULT_N_QUERIES = 5_000
WORKLOAD_SEED = 42
# Chosen per the B.5.1 sanity check (src/analysis/dataset_profile.py): 297 distinct
# values, top-10 share 59%, max/min frequency ratio ~99,000x — categorical, skewed,
# and non-trivial without being near-unique.
SENSITIVE_FIELD = "specific_diagnostic_test"

# Plan B.5: the three linked collections and the field that links them.
COLLECTIONS = ["patients", "lab_orders", "billing"]
LINK_FIELD = "patient_code"

# How aggressively C/D flatten frequency: every value's observed count is padded with
# decoys up toward `target_ratio` x the most frequent value's count (1.0 = fully flattened
# to uniform). This is an *experimental variable*, not a tuned constant: flattening harder
# lowers value-recovery but raises storage/latency overhead, so run_experiment.py sweeps
# DECOY_TARGET_RATIOS by default (for C/D only) to show that trade-off curve directly,
# rather than picking one ratio and reporting a single number.
DECOY_TARGET_RATIO = 0.5
DECOY_TARGET_RATIOS = [0.5, 0.75, 1.0]
