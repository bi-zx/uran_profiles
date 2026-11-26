#!/usr/bin/env python3
"""Render one autotask plugin for an existing URAN Runtime assembly."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--component-id", default="base")
    parser.add_argument("--instance-id", default="mission")
    parser.add_argument("--arbiter-instance", required=True)
    parser.add_argument("--python", required=True, help="Python in the environment where the autotask wheel is installed")
    parser.add_argument("--map-database", required=True, help="Persistent survey SQLite path on the device")
    parser.add_argument("--settings", type=Path, required=True, help="Device worker_config JSON with terrain and drive settings")
    args = parser.parse_args()

    settings = json.loads(args.settings.read_text(encoding="utf-8"))
    settings["device_id"] = args.device_id
    settings["arbiter_instance"] = args.arbiter_instance
    settings.setdefault("mapping", {})["map_database"] = args.map_database
    plugin = {
        "instance_id": args.instance_id, "device_id": args.device_id,
        "component_id": args.component_id, "plugin_type": "worker",
        "class_type": "uran_worker_adapter/WorkerProcessPlugin", "api_version": "2.1",
        "config": {
            "command": [args.python, "-I", "-m", "uran_worker_sdk", "uran_autotask_plugin.worker:worker_factory"],
            "message_types": ["uran.tasks.command.v1", "uran.sensors.observation.v1", "uran.operations.cancel.v1"],
            "capabilities": ["tasks.lifecycle", "tasks.area_explore", "tasks.map_patrol"],
            "worker_config": settings,
        },
    }
    print(json.dumps(plugin, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
