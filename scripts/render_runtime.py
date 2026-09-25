#!/usr/bin/env python3
"""Copy a profile runtime into a fixed deployment root."""
from __future__ import print_function

import os
import shutil
import sys


def main(argv):
    if len(argv) != 3:
        raise SystemExit("usage: render_runtime.py PROFILE_DIR OUTPUT_FILE")
    source = os.path.join(os.path.abspath(argv[1]), "runtime.yaml")
    target = os.path.abspath(argv[2])
    parent = os.path.dirname(target)
    if not os.path.isfile(source):
        raise SystemExit("missing profile runtime: %s" % source)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    shutil.copyfile(source, target)
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
