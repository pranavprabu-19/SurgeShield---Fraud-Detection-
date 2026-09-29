"""Keep pytest off the demo audit log, which a tamper click leaves broken on purpose."""

import os
import tempfile

os.environ.setdefault("SURGESHIELD_AUDIT_PATH", tempfile.mktemp(prefix="surgeshield-test-", suffix=".db"))
os.environ.setdefault("SURGESHIELD_HISTORY_PATH", tempfile.mktemp(prefix="surgeshield-hist-", suffix=".db"))
os.environ.setdefault("SURGESHIELD_UPLOAD_REPORTS", tempfile.mktemp(prefix="surgeshield-reports-", suffix=".json"))
