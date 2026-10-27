#!/usr/bin/env python3
"""Package an installed product assembly using the framework deployment tool.

This is a release-side operation; the target never fetches source repositories
or runs this script. Credentials and per-device calibration stay on the device.
"""
import argparse
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="assembled installed artifacts, not a repository checkout")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--deploy-tool", default="uran-deploy")
    args = parser.parse_args()
    source = Path(args.source).resolve()
    for path in source.rglob("*"):
        if path.name in {".git", "secrets.env", "device.json"}:
            raise SystemExit("release input contains source control or device secrets: " + str(path))
    tool = shutil.which(args.deploy_tool)
    if not tool:
        raise SystemExit("install uran-deploy from the framework SDK first")
    return subprocess.call([tool, "build-release", str(source), "--spec", args.spec,
        "--output", args.output, "--url", args.url,
        "--private-key", args.private_key, "--key-id", args.key_id])


if __name__ == "__main__":
    raise SystemExit(main())
