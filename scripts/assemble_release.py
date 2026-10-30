#!/usr/bin/env python3
"""Assemble an installed product release directory from a Profile, the framework SDK and wheels.

The output directory is the SOURCE of scripts/build_release.py (``uran-deploy
build-release``). Nothing here signs, uploads or touches a device.

Run it in an environment that matches the target exactly (architecture,
distribution, libc and the Python interpreter that runs this script): the
wheels are installed with this interpreter and ``build-release`` performs the
same platform check as the device.

Layout produced (the same as the bootstrap seed release plus product files)::

    bin/uran_runtime, lib/*.so*, share/uran_framework/plugins/worker/plugin.json   framework SDK
    python/                       wheels installed with --target, offline from a wheelhouse
    bin/<console scripts>         launchers generated from the product wheels' console_scripts
    bin/<launchers>               Profile bin/ (executable; a same-named file overrides the generated one)
    checks/<checks>               Profile checks/ (executable when they have a shebang)
    config/runtime.json           Profile runtime.json (managed JSON assembly)

Console scripts installed with --target embed the build host's interpreter, so
they are dropped and regenerated with the framework launcher pattern
(uran_deploy/packaging.py launcher()): add ../python to sys.path, call the entry point.
"""
from __future__ import print_function

import argparse
import configparser
from email.parser import HeaderParser
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
# Same runtime files as uran_framework uran_deploy/packaging.py copy_runtime_sdk().
SDK_FILES = ("bin/uran_runtime", "share/uran_framework/plugins/worker/plugin.json")
REFUSED_NAMES = {".git", "secrets.env", "device.json", "deployment.lock.json", "known_hosts", "authorized_keys"}
REFUSED_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
PLATFORM_KEYS = ("os", "arch", "distribution", "os_version", "python", "libc")
SPEC_KEYS = ("release_id", "profile_id", "profile_version", "api_version", "native_abi", "state_schema", "platform",
             "host", "runtime_config", "packages", "services", "checks", "preflight", "post_activate", "migration")


def sha256(path):
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def os_release():
    values = {}
    path = Path("/etc/os-release")
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip('"')
    return values


def build_platform():
    values = os_release()
    return {"os": platform.system(), "arch": platform.machine(), "distribution": values.get("ID"),
            "os_version": values.get("VERSION_ID"), "python": "%d.%d" % sys.version_info[:2],
            "libc": list(platform.libc_ver())}


def resolve_platform(draft, fill):
    """Keep the declared keys; null values are filled only when asked; every value must match this host."""
    current = build_platform()
    resolved = {}
    for key in PLATFORM_KEYS:
        if key not in draft:
            continue
        value = draft[key]
        if value is None:
            if not fill:
                raise ValueError("release platform %s is unknown; fill the draft or pass --platform-from-build-env" % key)
            value = current[key]
        if value != current[key]:
            raise ValueError("target %s %r does not match this build environment %r; assemble on a matching "
                             "environment" % (key, value, current[key]))
        resolved[key] = value
    if resolved.get("os") != "Linux" or not resolved.get("arch"):
        raise ValueError("release platform needs os Linux and arch")
    return resolved


def copy_sdk(sdk, out):
    for relative in SDK_FILES:
        source = sdk / relative
        if not source.is_file():
            raise ValueError("framework SDK is missing %s" % relative)
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(target))
    for path in sorted((sdk / "lib").glob("*.so*")):
        if path.is_file():
            (out / "lib").mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(path.resolve()), str(out / "lib" / path.name))
    if not os.access(str(out / "bin/uran_runtime"), os.X_OK):
        raise ValueError("framework SDK bin/uran_runtime is not executable")
    files = sorted(path for path in out.rglob("*") if path.is_file())
    lines = "".join("%s  %s\n" % (sha256(path), path.relative_to(out).as_posix()) for path in files)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def install_wheels(target, wheels, wheelhouse, installer, uv):
    if installer == "uv":
        command = [uv, "pip", "install", "--python", sys.executable, "--no-index", "--find-links", str(wheelhouse),
                   "--target", str(target)]
    else:
        command = [sys.executable, "-m", "pip", "install", "--no-index", "--find-links", str(wheelhouse),
                   "--target", str(target), "--no-compile", "--no-warn-script-location", "--disable-pip-version-check"]
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.check_call(command + [str(wheel) for wheel in wheels], env=environment)
    # Console-script shims carry the build host's interpreter path; release launchers live in bin/.
    shutil.rmtree(str(target / "bin"), ignore_errors=True)
    for cache in sorted(target.rglob("__pycache__"), reverse=True):
        shutil.rmtree(str(cache), ignore_errors=True)


LAUNCHER = ("#!/usr/bin/env python3\nimport pathlib, sys\n"
            "sys.dont_write_bytecode = True\n"
            "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'python'))\n"
            "from %s import %s\nraise SystemExit(%s())\n")


def generate_launchers(out, product_wheels):
    """Write bin/<name> for every console script of the product (not dependency) distributions."""
    products = {normalize(wheel.name.split("-")[0]) for wheel in product_wheels}
    generated = {}
    for dist in sorted((out / "python").glob("*.dist-info")):
        with open(str(dist / "METADATA"), "r", encoding="utf-8") as handle:
            if normalize(HeaderParser().parse(handle)["Name"]) not in products:
                continue
        entry_points = dist / "entry_points.txt"
        if not entry_points.is_file():
            continue
        parser = configparser.ConfigParser(delimiters=("=",))
        parser.optionxform = str
        parser.read(str(entry_points), encoding="utf-8")
        for name, target in (parser.items("console_scripts") if parser.has_section("console_scripts") else []):
            module, _, function = target.strip().partition(":")
            function = function.split("[")[0].strip()
            if not ID.match(name) or not module or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", function):
                raise ValueError("unsupported console script %s = %s" % (name, target))
            path = out / "bin" / name
            if path.exists():
                raise ValueError("console script %s collides with an SDK file" % name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(LAUNCHER % (module.strip(), function, function), encoding="utf-8")
            path.chmod(0o755)
            generated[name] = target.strip()
    return generated


def provenance(target, candidates):
    index = {}
    for wheel in candidates:
        parts = wheel.name[:-len(".whl")].split("-")
        if len(parts) >= 5:
            index[(normalize(parts[0]), parts[1])] = wheel
    packages = []
    for dist in sorted(target.glob("*.dist-info")):
        with open(str(dist / "METADATA"), "r", encoding="utf-8") as handle:
            meta = HeaderParser().parse(handle)
        name, version = meta["Name"], meta["Version"]
        wheel = index.get((normalize(name), version))
        if wheel is None:
            raise ValueError("installed distribution %s %s has no matching wheel" % (name, version))
        if not ID.match(name):
            raise ValueError("package name %r is not a URAN identifier" % name)
        packages.append({"package": name, "version": version, "origin": "wheel:" + wheel.name, "sha256": sha256(wheel)})
    return packages


def copy_profile(profile, out, extras, generated):
    overridden = []
    runtime_text = (profile / "runtime.json").read_text(encoding="utf-8")
    runtime = json.loads(runtime_text)  # managed releases use JSON assemblies
    (out / "config").mkdir(parents=True, exist_ok=True)
    (out / "config/runtime.json").write_text(runtime_text, encoding="utf-8")
    for part in ("bin", "checks"):
        root = profile / part
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("profile %s contains a symbolic link: %s" % (part, path))
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            target = out / part / path.relative_to(root)
            if target.exists() and part == "bin" and path.name in generated:
                overridden.append(path.name)       # product wrapper replaces the generated launcher
                target.unlink()
            elif target.exists():
                raise ValueError("profile file collides with SDK file: %s" % target.relative_to(out))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(path), str(target))
            executable = part == "bin" or path.read_bytes()[:2] == b"#!"
            target.chmod(0o755 if executable else 0o644)
    for source, destination in extras:
        source_path = (profile / source).resolve()
        source_path.relative_to(profile.resolve())
        if destination.startswith("/") or ".." in Path(destination).parts:
            raise ValueError("extra destination must be release-relative: %s" % destination)
        target = out / destination
        if target.exists():
            raise ValueError("extra destination already exists: %s" % destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(str(source_path), str(target))
        else:
            shutil.copyfile(str(source_path), str(target))
    return runtime, overridden


def refuse_sensitive(out):
    for path in out.rglob("*"):
        if path.is_symlink():
            raise ValueError("release input contains a symbolic link: %s" % path.relative_to(out))
        if path.name in REFUSED_NAMES or path.name.endswith(REFUSED_SUFFIXES):
            raise ValueError("release input contains source control or device secrets: %s" % path.relative_to(out))


def check_references(out, runtime, spec):
    warnings = []
    for plugin in runtime.get("plugins", []):
        command = plugin.get("config", {}).get("command") or []
        if command and str(command[0]).startswith("${release}/"):
            path = out / command[0][len("${release}/"):]
            if not path.is_file() or not os.access(str(path), os.X_OK):
                raise ValueError("instance %s launches %s, which is not an executable file in the release"
                                 % (plugin.get("instance_id"), command[0]))
        elif command:
            warnings.append("instance %s starts %s from outside the release" % (plugin.get("instance_id"), command[0]))
    for key in ("preflight", "checks", "post_activate"):
        for item in spec.get(key) or []:
            path = out / item["command"][0]
            if not path.is_file() or not os.access(str(path), os.X_OK):
                raise ValueError("%s command %s is not an executable file in the release" % (key, item["command"][0]))
    for key in ("host", "runtime_config"):
        if not (out / spec[key]).is_file():
            raise ValueError("%s %s is missing from the release" % (key, spec[key]))
    return warnings


def build_spec(draft, args, platform_values, packages):
    spec = {key: draft.get(key) for key in SPEC_KEYS}
    spec["release_id"] = args.release_id or draft.get("release_id")
    spec["profile_version"] = args.profile_version or draft.get("profile_version")
    spec["platform"] = platform_values
    spec["packages"] = packages
    spec["host"] = spec["host"] or "bin/uran_runtime"
    spec["runtime_config"] = spec["runtime_config"] or "config/runtime.json"
    spec["api_version"], spec["native_abi"] = "2.1", 3
    for key, default in (("services", []), ("checks", []), ("preflight", []), ("post_activate", [])):
        spec[key] = spec[key] if spec[key] is not None else default
    for key in ("release_id", "profile_id", "profile_version", "state_schema"):
        if not isinstance(spec[key], str) or not ID.match(spec[key]):
            raise ValueError("%s is missing or invalid: %r" % (key, spec[key]))
    return spec


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("profile", help="profiles/<profile_id> directory")
    parser.add_argument("--sdk-prefix", required=True, help="installed framework SDK prefix")
    parser.add_argument("--sdk-version", required=True)
    parser.add_argument("--sdk-ref", required=True, help="framework version or commit recorded as package origin")
    parser.add_argument("--wheel", action="append", required=True, help="product plugin wheel (repeatable)")
    parser.add_argument("--wheelhouse", required=True, help="locked dependency wheels; installation is offline")
    parser.add_argument("--output", required=True, help="new or empty directory outside the repository")
    parser.add_argument("--spec-out", required=True, help="release spec for build_release.py")
    parser.add_argument("--draft", help="default: <profile>/release/release-spec.draft.json")
    parser.add_argument("--release-id")
    parser.add_argument("--profile-version")
    parser.add_argument("--installer", choices=("pip", "uv"), default="pip")
    parser.add_argument("--uv", default="uv", help="uv executable when --installer uv")
    parser.add_argument("--platform-from-build-env", action="store_true",
                        help="fill null platform values from this (matching) build environment")
    parser.add_argument("--extra", action="append", default=[], metavar="SRC=DEST",
                        help="additional profile file or directory copied to a release-relative path")
    args = parser.parse_args(argv)
    profile, out = Path(args.profile).resolve(), Path(args.output).resolve()
    spec_out = Path(args.spec_out).resolve()
    try:
        if out.exists() and any(out.iterdir()):
            raise ValueError("output directory must be new or empty")
        if profile == out or profile in out.parents or out in spec_out.parents:
            raise ValueError("output must be outside the profile, and the spec outside the output")
        draft_path = Path(args.draft) if args.draft else profile / "release/release-spec.draft.json"
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        if draft.get("profile_id") != profile.name:
            raise ValueError("draft profile_id %r does not match the profile directory %r" % (draft.get("profile_id"), profile.name))
        extras = []
        for item in args.extra:
            if "=" not in item:
                raise ValueError("--extra expects SRC=DEST")
            extras.append(tuple(item.split("=", 1)))
        platform_values = resolve_platform(draft.get("platform") or {}, args.platform_from_build_env)
        out.mkdir(parents=True, exist_ok=True)
        sdk_digest = copy_sdk(Path(args.sdk_prefix), out)
        wheels = [Path(wheel).resolve() for wheel in args.wheel]
        wheelhouse = Path(args.wheelhouse).resolve()
        install_wheels(out / "python", wheels, wheelhouse, args.installer, args.uv)
        packages = [{"package": "uran-framework", "version": args.sdk_version, "origin": args.sdk_ref, "sha256": sdk_digest}]
        packages += provenance(out / "python", wheels + sorted(wheelhouse.glob("*.whl")))
        generated = generate_launchers(out, wheels)
        runtime, overridden = copy_profile(profile, out, extras, generated)
        refuse_sensitive(out)
        spec = build_spec(draft, args, platform_values, packages)
        warnings = check_references(out, runtime, spec)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit("release assembly failed: %s" % error)
    spec_out.parent.mkdir(parents=True, exist_ok=True)
    spec_out.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for warning in warnings:
        print("warning: " + warning, file=sys.stderr)
    print(json.dumps({"assembly": str(out), "spec": str(spec_out), "release_id": spec["release_id"],
                      "launchers": sorted(set(generated) - set(overridden)), "profile_launchers": overridden,
                      "packages": [item["package"] + "==" + item["version"] for item in packages]}, indent=2))
    print("next: python3 scripts/build_release.py %s --spec %s --url <https artifact URL> "
          "--private-key <publisher key> --key-id <key id> --output <archive outside the assembly>" % (out, spec_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
