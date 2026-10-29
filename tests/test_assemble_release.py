import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

import pytest


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("assemble_release", REPO / "scripts/assemble_release.py")
assembler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembler)

needs_pip = pytest.mark.skipif(importlib.util.find_spec("pip") is None, reason="pip is required to install wheels")


def make_wheel(directory, name, version, module, code, requires=(), scripts=None):
    dist = name.replace("-", "_")
    info = "%s-%s.dist-info" % (dist, version)
    files = {
        "%s/__init__.py" % module: code,
        info + "/METADATA": "Metadata-Version: 2.1\nName: %s\nVersion: %s\n%s" % (
            name, version, "".join("Requires-Dist: %s\n" % item for item in requires)),
        info + "/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    if scripts:
        files[info + "/entry_points.txt"] = "[console_scripts]\n" + "".join(
            "%s = %s\n" % item for item in scripts.items())
    record = []
    path = directory / ("%s-%s-py3-none-any.whl" % (dist, version))
    with zipfile.ZipFile(str(path), "w") as archive:
        for member, text in files.items():
            data = text.encode("utf-8")
            archive.writestr(member, data)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            record.append("%s,sha256=%s,%d" % (member, digest, len(data)))
        record.append(info + "/RECORD,,")
        archive.writestr(info + "/RECORD", "\n".join(record) + "\n")
    return path


@pytest.fixture
def workspace(tmp_path):
    sdk = tmp_path / "sdk"
    (sdk / "bin").mkdir(parents=True)
    (sdk / "bin/uran_runtime").write_text("#!/bin/sh\nexit 0\n")
    (sdk / "bin/uran_runtime").chmod(0o755)
    (sdk / "share/uran_framework/plugins/worker").mkdir(parents=True)
    (sdk / "share/uran_framework/plugins/worker/plugin.json").write_text(json.dumps(
        {"schema_version": 1, "package": "worker", "version": "2.1.0", "api_version": "2.1", "plugins": []}))
    (sdk / "lib").mkdir()
    (sdk / "lib/liburan_core.so.2").write_bytes(b"\x7fELF-stub")
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    plugin = make_wheel(wheels, "demo-plugin", "0.1.0", "demo_plugin",
                        "import demo_dep\n\ndef main():\n    return 0 if demo_dep.VALUE == 1 else 3\n",
                        requires=("demo-dep>=1",), scripts={"uran-demo-worker": "demo_plugin:main"})
    make_wheel(wheels, "demo-dep", "1.2.0", "demo_dep", "VALUE = 1\n",
               scripts={"demo-dep-tool": "demo_dep:tool"})
    profile = tmp_path / "profiles" / "demo_robot"
    (profile / "bin").mkdir(parents=True)
    (profile / "checks").mkdir()
    (profile / "release").mkdir()
    (profile / "bin/uran-demo-worker").write_text(
        "#!/usr/bin/env python3\n# product wrapper\nimport pathlib, sys\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'python'))\n"
        "from demo_plugin import main\nraise SystemExit(main())\n")
    (profile / "checks/health.py").write_text("#!/usr/bin/env python3\nraise SystemExit(0)\n")
    runtime = {"default_device_id": "${device_id}", "plugin_manifests": [],
               "components": [{"component_id": "base", "instances": ["demo_motion"], "requires": ["motion.base.velocity"]}],
               "plugins": [{"instance_id": "demo_motion", "device_id": "${device_id}", "component_id": "base",
                            "class_type": "uran_worker_adapter/WorkerProcessPlugin",
                            "config": {"command": ["${release}/bin/uran-demo-worker"],
                                       "message_types": ["uran.motion.command.v1"],
                                       "capabilities": ["motion.base.velocity"]}}]}
    (profile / "runtime.json").write_text(json.dumps(runtime))
    current = assembler.build_platform()
    draft = {"release_id": None, "profile_id": "demo_robot", "profile_version": "0.1.0", "api_version": "2.1",
             "native_abi": 3, "state_schema": "1",
             "platform": {"os": current["os"], "arch": current["arch"], "python": current["python"]},
             "host": "bin/uran_runtime", "runtime_config": "config/runtime.json",
             "packages": [{"package": "demo-plugin", "version": "0.1.0", "origin": None, "sha256": None}],
             "services": [], "preflight": [{"command": ["checks/health.py"], "timeout_s": 10}],
             "checks": [{"command": ["checks/health.py"], "timeout_s": 10}], "post_activate": [], "migration": None}
    (profile / "release/release-spec.draft.json").write_text(json.dumps(draft))
    return {"root": tmp_path, "sdk": sdk, "wheels": wheels, "plugin": plugin, "profile": profile}


def run(workspace, *extra):
    out = workspace["root"] / "assembly"
    spec_out = workspace["root"] / "spec.json"
    code = assembler.main([str(workspace["profile"]), "--sdk-prefix", str(workspace["sdk"]), "--sdk-version", "2.1.0",
                           "--sdk-ref", "uran_framework@test", "--wheel", str(workspace["plugin"]),
                           "--wheelhouse", str(workspace["wheels"]), "--output", str(out), "--spec-out", str(spec_out),
                           "--release-id", "demo_robot-0.1.0"] + list(extra))
    return code, out, json.loads(spec_out.read_text())


@needs_pip
def test_assembles_layout_and_records_provenance(workspace):
    code, out, release_spec = run(workspace)
    assert code == 0
    assert os.access(str(out / "bin/uran_runtime"), os.X_OK) and (out / "lib/liburan_core.so.2").is_file()
    assert (out / "share/uran_framework/plugins/worker/plugin.json").is_file()
    assert (out / "python/demo_plugin/__init__.py").is_file() and (out / "python/demo_dep/__init__.py").is_file()
    assert not (out / "python/bin").exists() and not list(out.rglob("__pycache__"))
    assert os.access(str(out / "bin/uran-demo-worker"), os.X_OK) and os.access(str(out / "checks/health.py"), os.X_OK)
    assert json.loads((out / "config/runtime.json").read_text())["plugins"][0]["instance_id"] == "demo_motion"
    packages = {item["package"]: item for item in release_spec["packages"]}
    assert set(packages) == {"uran-framework", "demo-plugin", "demo-dep"}
    assert packages["demo-plugin"]["sha256"] == assembler.sha256(workspace["plugin"])
    assert packages["demo-dep"]["origin"] == "wheel:demo_dep-1.2.0-py3-none-any.whl"
    assert release_spec["release_id"] == "demo_robot-0.1.0" and release_spec["platform"]["os"] == "Linux"


@needs_pip
def test_refuses_device_secrets(workspace):
    (workspace["profile"] / "checks/secrets.env").write_text("TOKEN=x\n")
    with pytest.raises(SystemExit, match="secrets"):
        run(workspace)


def test_refuses_mismatched_target_platform(workspace):
    draft_path = workspace["profile"] / "release/release-spec.draft.json"
    draft = json.loads(draft_path.read_text())
    draft["platform"]["arch"] = "not-this-arch"
    draft_path.write_text(json.dumps(draft))
    with pytest.raises(SystemExit, match="does not match this build environment"):
        run(workspace)


@needs_pip
def test_null_platform_needs_explicit_fill(workspace):
    draft_path = workspace["profile"] / "release/release-spec.draft.json"
    draft = json.loads(draft_path.read_text())
    draft["platform"]["arch"] = None
    draft_path.write_text(json.dumps(draft))
    with pytest.raises(SystemExit, match="unknown"):
        run(workspace)
    shutil.rmtree(str(workspace["root"] / "assembly"), ignore_errors=True)
    code, _, release_spec = run(workspace, "--platform-from-build-env")
    assert code == 0 and release_spec["platform"]["arch"] == assembler.build_platform()["arch"]


@needs_pip
def test_profile_wrapper_overrides_the_generated_launcher(workspace):
    _, out, _ = run(workspace)
    assert "# product wrapper" in (out / "bin/uran-demo-worker").read_text()
    assert not (out / "bin/demo-dep-tool").exists()          # dependency console scripts are not exposed


@needs_pip
def test_launcher_is_generated_from_the_console_script(workspace):
    (workspace["profile"] / "bin/uran-demo-worker").unlink()
    _, out, _ = run(workspace)
    launcher = out / "bin/uran-demo-worker"
    assert os.access(str(launcher), os.X_OK) and "from demo_plugin import main" in launcher.read_text()
    environment = {key: value for key, value in os.environ.items() if not key.startswith(("PYTHON", "LD_"))}
    assert subprocess.call([sys.executable, str(launcher)], env=environment) == 0


@needs_pip
def test_launcher_referenced_by_runtime_must_exist(workspace):
    runtime_path = workspace["profile"] / "runtime.json"
    runtime = json.loads(runtime_path.read_text())
    runtime["plugins"][0]["config"]["command"] = ["${release}/bin/uran-missing-worker"]
    runtime_path.write_text(json.dumps(runtime))
    with pytest.raises(SystemExit, match="not an executable file"):
        run(workspace)


def test_output_must_be_empty(workspace):
    out = workspace["root"] / "assembly"
    out.mkdir()
    (out / "left-over").write_text("x")
    with pytest.raises(SystemExit, match="new or empty"):
        run(workspace)


@needs_pip
@pytest.mark.skipif(importlib.util.find_spec("uran_deploy") is None or shutil.which("openssl") is None,
                    reason="uran_deploy and openssl are required for the build-release round trip")
def test_build_release_round_trip_passes_device_side_validation(workspace):
    from uran_deploy.artifacts import extract, validate_release
    from uran_deploy.packaging import build_release
    from uran_deploy.security import Authority

    _, out, release_spec = run(workspace)
    keys = workspace["root"] / "keys"
    keys.mkdir()
    subprocess.check_call(["openssl", "genrsa", "-out", str(keys / "publisher.key.pem"), "3072"], stderr=subprocess.DEVNULL)
    subprocess.check_call(["openssl", "rsa", "-in", str(keys / "publisher.key.pem"), "-pubout",
                           "-out", str(keys / "publisher.pub.pem")], stderr=subprocess.DEVNULL)
    archive = workspace["root"] / "dist" / "demo_robot-0.1.0.tar.gz"
    envelope = build_release(out, release_spec, archive, "https://artifacts.example.com/demo_robot-0.1.0.tar.gz",
                             keys / "publisher.key.pem", "publisher-test")
    # Device side, in the order of uran_deploy engine._stage(): signature, digest, extraction, lock.
    authority = Authority({"trust": {"publisher-test": {"role": "publisher", "subject": "release",
                                                        "public_key": str(keys / "publisher.pub.pem")}}},
                          workspace["root"])
    release, _ = authority.release(envelope)
    assert release["artifact"]["sha256"] == assembler.sha256(archive)
    staging = workspace["root"] / "staging"
    extract(archive, staging, {})
    lock = validate_release(staging, release, {})
    assert {item["package"] for item in lock["packages"]} == {"uran-framework", "demo-plugin", "demo-dep"}
    # Tampering with any packaged file is caught by the same device-side validation.
    (staging / "python/demo_dep/__init__.py").write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="failed verification"):
        validate_release(staging, release, {})
    with tarfile.open(str(archive)) as bundle:
        assert "deployment.lock.json" in bundle.getnames()
