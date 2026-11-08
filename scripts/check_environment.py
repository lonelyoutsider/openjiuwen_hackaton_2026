"""Print local prerequisites without network calls or secret values.

Usage: python scripts/check_environment.py
This is not an integration test and does not load .env files automatically.
"""

import importlib.metadata
import json
import os
import shutil
import sys


def main():
    packages = {}
    for package in ("workswarm", "openjiuwen", "openai", "scikit-learn", "catboost"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "not installed (not yet required)"
    result = {
        "python": ".".join(map(str, sys.version_info[:3])),
        "recommended_python_3_11_or_3_12": sys.version_info[:2] in ((3, 11), (3, 12)),
        "git_available": shutil.which("git") is not None,
        "packages": packages,
        "environment_variables_present": {
            key: bool(os.environ.get(key))
            for key in ("NEURALDEEP_BASE_URL", "NEURALDEEP_API_KEY", "NEURALDEEP_MODEL")
        },
        "network_tested": False,
        "competition_dependencies_confirmed": False,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
