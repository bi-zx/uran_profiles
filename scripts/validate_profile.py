#!/usr/bin/env python3
"""Validate the CyberDog2 profile without contacting hardware."""
from __future__ import print_function

import os
import sys

try:
    import yaml
except ImportError:
    yaml = None


REQUIRED = ("profile.yaml", "runtime.yaml")


def fail(message):
    raise SystemExit("profile validation failed: %s" % message)


def main(argv):
    if len(argv) != 2:
        fail("usage: validate_profile.py PROFILE_DIR")
    if yaml is None:
        fail("PyYAML is required")
    root = os.path.abspath(argv[1])
    for name in REQUIRED:
        if not os.path.isfile(os.path.join(root, name)):
            fail("missing %s" % name)
    with open(os.path.join(root, "profile.yaml")) as stream:
        profile = yaml.safe_load(stream) or {}
    with open(os.path.join(root, "runtime.yaml")) as stream:
        runtime = yaml.safe_load(stream) or {}
    if profile.get("profile_id") != "cyberdog2":
        fail("profile_id must be cyberdog2")
    identity = profile.get("identity") or {}
    if identity.get("device_id") != "device_001":
        fail("device identity must come from /SDCARD/uran_ws")
    components = [item.get("component_id") for item in profile.get("components", [])]
    if "base" not in components:
        fail("base component is missing")
    if "arm" not in components:
        fail("arm component is missing")
    plugins = runtime.get("plugins") or []
    ids = [item.get("instance_id") for item in plugins]
    if len(ids) != len(set(ids)):
        fail("plugin instance IDs must be unique")
    motion = [item for item in plugins if item.get("instance_id") == "cyberdog2_motion"]
    if len(motion) != 1 or motion[0].get("component_id") != "base":
        fail("CyberDog2 motion must target component base")
    arms = [item for item in plugins if item.get("instance_id") == "so101_arm"]
    if len(arms) != 1 or arms[0].get("component_id") != "arm":
        fail("SO101 arm plugin must target component arm")
    arm_config = ((arms[0].get("config") or {}).get("worker_config") or {})
    if arm_config.get("serial_port") in (None, ""):
        fail("SO101 serial_port must be present in worker_config")
    if not runtime.get("plugin_manifests"):
        fail("plugin_manifests is required")
    print("profile OK: %s (%d plugins, base and arm)" %
          (profile.get("profile_version", "unknown"), len(plugins)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
