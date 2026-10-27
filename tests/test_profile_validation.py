import copy
import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_profile", REPO / "scripts/validate_profile.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def assembly():
    profile = {"schema_version": "1.0", "profile_id": "warehouse-cart", "profile_version": "1.0.0",
        "identity": {"device_id": "cart_027"},
        "components": [{"component_id": "drive", "motion_instance": "drive_control"}],
        "services": [{"instance_id": "transport"}]}
    runtime = {"default_device_id": "cart_027", "primary_protocol_instance": "transport",
        "plugin_manifests": ["${release}/plugins/worker.json"], "plugins": [
            {"instance_id": "drive_control", "component_id": "drive",
             "class_type": "uran_worker_adapter/WorkerProcessPlugin"},
            {"instance_id": "transport", "component_id": "communication",
             "class_type": "uran_worker_adapter/WorkerProtocolPlugin"}]}
    return profile, runtime


def test_another_product_without_base_or_arm():
    assert validator.validate(*assembly()) == {"profile_id": "warehouse-cart", "components": 1, "plugins": 2}


def test_empty_profile_needs_no_motion_or_protocol(tmp_path):
    (tmp_path / "profile.json").write_text(json.dumps({"schema_version": "1.0",
        "profile_id": "empty", "profile_version": "1.0.0"}))
    (tmp_path / "runtime.json").write_text("{}")
    assert validator.validate_directory(tmp_path) == {"profile_id": "empty", "components": 0, "plugins": 0}


def test_local_device_placeholder_is_supported():
    profile, runtime = assembly()
    runtime["default_device_id"] = "${device_id}"
    runtime["plugins"][0]["device_id"] = "${device_id}"
    validator.validate(profile, runtime)


@pytest.mark.parametrize("change, message", [
    ("duplicate_instance", "instance IDs must be unique"),
    ("unknown_motion", "missing or mismatched plugin"),
    ("wrong_component", "missing or mismatched plugin"),
    ("unknown_service", "missing or duplicate plugin"),
    ("wrong_device", "identities differ"),
    ("component_cycle", "cycle or missing parent"),
])
def test_invalid_assembly_references_are_rejected(change, message):
    profile, runtime = assembly()
    if change == "duplicate_instance":
        runtime["plugins"].append(copy.deepcopy(runtime["plugins"][0]))
    elif change == "unknown_motion":
        profile["components"][0]["motion_instance"] = "unknown"
    elif change == "wrong_component":
        runtime["plugins"][0]["component_id"] = "other"
    elif change == "unknown_service":
        profile["services"][0]["instance_id"] = "unknown"
    elif change == "wrong_device":
        runtime["default_device_id"] = "another_robot"
    elif change == "component_cycle":
        profile["components"][0]["parent_component_id"] = "drive"
    with pytest.raises(ValueError, match=message):
        validator.validate(profile, runtime)
