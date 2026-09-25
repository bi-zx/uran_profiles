#!/bin/bash
set -eu

URAN_ROOT="${URAN_ROOT:-/SDCARD/URAN/current}"
export URAN_ROOT
export URAN_INTERFACES_SCHEMA_DIR="${URAN_INTERFACES_SCHEMA_DIR:-$URAN_ROOT/source/uran_interfaces/schemas}"
# Keep target-only wheels (jsonschema/pyrsistent) in the deployment root while
# leaving the system Python installation untouched. This is required on the
# CyberDog2 Python 3.6 image, which does not ship jsonschema.
export PYTHONPATH="/SDCARD/URAN/python:$URAN_ROOT/source/uran_framework/python/uran_worker_sdk:$URAN_ROOT/source/uran_interfaces/bindings/python:$PYTHONPATH"
export PYTHONUNBUFFERED=1
