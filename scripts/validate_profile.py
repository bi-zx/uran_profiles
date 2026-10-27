#!/usr/bin/env python3
"""Validate product assembly structure without importing robot backends."""
from __future__ import print_function

import json
from pathlib import Path
import re
import sys


PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
RUNTIME_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def load_document(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    try:
        return json.loads(text)
    except ValueError:
        try:
            import yaml
        except ImportError:
            raise ValueError("PyYAML is required to validate YAML profiles")
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            raise ValueError("invalid YAML document: " + str(path))


def mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    return value


def records(value, label):
    if not isinstance(value, list):
        raise ValueError(label + " must be an array")
    return [mapping(item, label + " entry") for item in value]


def identifier(value, label, pattern=RUNTIME_ID):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(label + " is missing or invalid")
    return value


def device_identifier(value):
    if value != "${device_id}":
        identifier(value, "device_id")
    return value


def same_device(first, second):
    return first == second or "${device_id}" in (first, second)


def validate(profile, runtime):
    mapping(profile, "profile")
    mapping(runtime, "runtime")
    if profile.get("schema_version") != "1.0":
        raise ValueError("unsupported profile schema_version")
    identifier(profile.get("profile_id"), "profile_id", PROFILE_ID)
    identifier(profile.get("profile_version"), "profile_version", PROFILE_ID)
    identity = mapping(profile.get("identity", {}), "identity")
    device = identity.get("device_id", runtime.get("default_device_id"))
    if device is not None:
        device_identifier(device)
    default_device = runtime.get("default_device_id", device)
    if default_device is not None:
        device_identifier(default_device)
    if device is not None and not same_device(default_device, device):
        raise ValueError("profile and runtime device identities differ")

    components = {}
    for item in records(profile.get("components", []), "components"):
        name = identifier(item.get("component_id"), "component_id")
        if name in components:
            raise ValueError("component IDs must be unique")
        components[name] = item
    for name in components:
        cursor, seen = name, set()
        while cursor is not None:
            identifier(cursor, "parent_component_id")
            if cursor in seen or cursor not in components:
                raise ValueError("component parents contain a cycle or missing parent")
            seen.add(cursor)
            cursor = components[cursor].get("parent_component_id")

    plugins = {}
    for item in records(runtime.get("plugins", []), "plugins"):
        name = identifier(item.get("instance_id"), "instance_id")
        if name in plugins:
            raise ValueError("plugin instance IDs must be unique")
        identifier(item.get("component_id"), "plugin component_id")
        plugin_device = item.get("device_id", default_device)
        if plugin_device is not None:
            device_identifier(plugin_device)
        if device is not None and not same_device(plugin_device, device):
            raise ValueError("plugin device identity differs from profile")
        if not isinstance(item.get("class_type"), str) or not item["class_type"]:
            raise ValueError("plugin class_type is missing")
        mapping(item.get("config", {}), "plugin config")
        plugins[name] = item
    for name, component in components.items():
        references = component.get("instances", [])
        if not isinstance(references, list):
            raise ValueError("component instances must be an array")
        if component.get("motion_instance") is not None:
            references = references + [component["motion_instance"]]
        for instance in references:
            identifier(instance, "component instance reference")
            if instance not in plugins or plugins[instance]["component_id"] != name:
                raise ValueError("component references a missing or mismatched plugin")

    services = set()
    for service in records(profile.get("services", []), "services"):
        name = identifier(service.get("instance_id"), "service instance_id")
        if name in services or name not in plugins:
            raise ValueError("service references a missing or duplicate plugin")
        services.add(name)
    primary = runtime.get("primary_protocol_instance")
    if primary is not None:
        identifier(primary, "primary_protocol_instance")
        if primary not in plugins:
            raise ValueError("primary protocol references a missing plugin")
    manifests = runtime.get("plugin_manifests", [])
    if not isinstance(manifests, list) or any(not isinstance(path, str) or not path for path in manifests):
        raise ValueError("plugin_manifests must be an array of paths")
    if plugins and not manifests:
        raise ValueError("plugin_manifests is required when plugins are configured")
    return {"profile_id": profile["profile_id"], "components": len(components), "plugins": len(plugins)}


def validate_directory(directory):
    root = Path(directory)
    profile_file = next((root / name for name in ("profile.yaml", "profile.json")
                         if (root / name).is_file()), None)
    runtime_file = next((root / name for name in ("runtime.yaml", "runtime.json")
                         if (root / name).is_file()), None)
    if profile_file is None or runtime_file is None:
        raise ValueError("profile and runtime documents are required")
    return validate(load_document(profile_file), load_document(runtime_file))


def main(argv):
    if len(argv) != 2:
        raise SystemExit("usage: validate_profile.py PROFILE_DIR")
    try:
        result = validate_directory(argv[1])
    except (ValueError, OSError) as error:
        raise SystemExit("profile validation failed: " + str(error))
    print("profile OK: {profile_id} ({components} components, {plugins} plugins)".format(**result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
