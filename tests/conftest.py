import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"

# util.py imports only stdlib + requests, so it is importable without the
# zendriver/ddddocr stack that pins the bot itself to Python 3.10-3.11.
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
