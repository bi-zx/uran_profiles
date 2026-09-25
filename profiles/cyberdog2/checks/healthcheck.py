#!/usr/bin/env python3
"""Non-destructive CyberDog2 checks for the deployed profile."""
from __future__ import print_function

import os
import subprocess
import sys


NAMESPACE = "/mi_desktop_48_b0_2d_5f_b6_d0"


def run(*args):
    try:
        return subprocess.check_output(args, stderr=subprocess.STDOUT,
                                       universal_newlines=True, timeout=20)
    except Exception as exc:
        return "ERROR: %s" % exc


def main():
    print("profile_root=%s" % os.environ.get("URAN_ROOT", "/SDCARD/URAN/current"))
    print("nodes:")
    print(run("bash", "-lc", "source /etc/mi/ros2_env.conf; ros2 node list"))
    print("required_topics:")
    for topic in (NAMESPACE + "/motion_status", NAMESPACE + "/bms_status",
                  NAMESPACE + "/image", NAMESPACE + "/img_trans_signal_in",
                  NAMESPACE + "/img_trans_signal_out"):
        print("%s: %s" % (topic, run("bash", "-lc",
            "source /etc/mi/ros2_env.conf; ros2 topic type '%s'" % topic).strip()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
