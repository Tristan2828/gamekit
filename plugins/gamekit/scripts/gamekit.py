"""gamekit command line. Usage: python gamekit.py -h"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamekit_lib.cli import main  # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # output piped into something that stopped reading (e.g. `| head`)
        sys.stderr.close()
        sys.exit(0)
