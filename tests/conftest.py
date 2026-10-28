import os
import tempfile

# Point the processing-record database at a throwaway file before any app
# module is imported, so tests never touch ./flowbit.db.
_tmp_dir = tempfile.mkdtemp(prefix="flowbit-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp_dir, 'records.db')}"
os.environ["FLOWBIT_CHECKPOINT_DB"] = os.path.join(_tmp_dir, "checkpoints.db")
os.environ["FLOWBIT_LLM_PROVIDER"] = "fake"
os.environ.pop("GOOGLE_API_KEY", None)
