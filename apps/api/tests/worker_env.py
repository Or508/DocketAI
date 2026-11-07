"""Test helper. Prints the environment key names the worker process received."""

import json
import os

print(json.dumps({"ok": True, "pages": 1, "keys": sorted(os.environ)}), flush=True)
