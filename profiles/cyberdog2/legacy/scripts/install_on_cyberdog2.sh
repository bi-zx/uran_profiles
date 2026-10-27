#!/bin/bash
set -e

# Run on CyberDog2 as user mi. The old /SDCARD/uran_ws is read-only input;
# /SDCARD/ARM is intentionally never consulted.
ROOT="${URAN_DEPLOY_ROOT:-/SDCARD/URAN}"
if [ -f "$ROOT/active.json" ]; then
  echo "managed URAN deployment detected; submit a signed release through Core instead" >&2
  exit 2
fi
VERSION="${URAN_PROFILE_VERSION:-cyberdog2-0.1.0}"
RELEASE="$ROOT/releases/$VERSION"

mkdir -p "$ROOT/releases" "$ROOT/source" "$ROOT/config" "$ROOT/state"
if [ -e "$RELEASE" ]; then
  echo "release already exists: $RELEASE" >&2
  exit 2
fi
mkdir -p "$RELEASE/runtime/bin" "$RELEASE/install" "$RELEASE/state" "$RELEASE/config"

copy_tree() {
  name="$1"
  destination="$RELEASE/source/$name"
  mkdir -p "$destination"
  cp -a "$ROOT/source/$name/." "$destination/"
}

for repo in uran_framework uran_interfaces uran_plugins uran_ros2_adapter uran_profiles; do
  copy_tree "$repo"
done

RELEASE_PROFILE="$RELEASE/source/uran_profiles/profiles/cyberdog2"
for launcher in uran-mqtt-worker uran-cyberdog2-worker uran-media-worker \
                uran-so101-worker uran-so101-calibrate worker-env.sh start-cyberdog2.sh; do
  cp "$RELEASE_PROFILE/legacy/scripts/$launcher" "$RELEASE/runtime/bin/"
done
chmod 755 "$RELEASE/runtime/bin"/*

umask 077
python3 - "$RELEASE/config/secrets.env" <<'PY'
import os
import sys

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required to read the original network config: %s" % exc)

source = "/SDCARD/uran_ws/src/uran_core/config/network.yaml"
with open(source) as stream:
    data = yaml.safe_load(stream) or {}
network = data.get("network") or {}
auth = network.get("auth") or {}

def value(name):
    item = auth.get(name, "")
    return "" if item is None else str(item)

with open(sys.argv[1], "w") as stream:
    stream.write("URAN_MQTT_USERNAME=%s\n" % value("username").replace("\\", "\\\\").replace("\n", ""))
    stream.write("URAN_MQTT_TOKEN=%s\n" % value("token").replace("\\", "\\\\").replace("\n", ""))
os.chmod(sys.argv[1], 0o600)
PY
cp "$RELEASE/config/secrets.env" "$ROOT/config/secrets.env"
chmod 600 "$ROOT/config/secrets.env"

python3 "$RELEASE/source/uran_profiles/scripts/validate_profile.py" \
  "$RELEASE_PROFILE"
python3 "$RELEASE_PROFILE/checks/validate_legacy.py" "$RELEASE_PROFILE"

echo "building uran_framework"
export COLCON_TRACE="${COLCON_TRACE:-}"
source /etc/mi/ros2_env.conf
source /opt/ros2/galactic/setup.bash
cmake -S "$RELEASE/source/uran_framework" -B "$RELEASE/build/framework" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$RELEASE/install/framework" \
  -DBUILD_TESTING=OFF -DURAN_BUILD_NATIVE=ON -DURAN_FETCH_DEPENDENCIES=OFF \
  -DCMAKE_PREFIX_PATH=/SDCARD/URAN/deps/nlohmann/usr \
  -Dnlohmann_json_DIR=/SDCARD/URAN/deps/nlohmann/usr/lib/cmake/nlohmann_json
cmake --build "$RELEASE/build/framework" --parallel 2
cmake --install "$RELEASE/build/framework"

echo "building uran_interfaces"
cmake -S "$RELEASE/source/uran_interfaces" -B "$RELEASE/build/interfaces" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$RELEASE/install/interfaces" \
  -DBUILD_TESTING=OFF \
  -DCMAKE_PREFIX_PATH=/SDCARD/URAN/deps/nlohmann/usr \
  -Dnlohmann_json_DIR=/SDCARD/URAN/deps/nlohmann/usr/lib/cmake/nlohmann_json
cmake --build "$RELEASE/build/interfaces" --parallel 2
cmake --install "$RELEASE/build/interfaces"

echo "building uran_ros2_adapter"
export AMENT_PREFIX_PATH="$RELEASE/install/framework:$RELEASE/install/interfaces:${AMENT_PREFIX_PATH:-}"
export CMAKE_PREFIX_PATH="$RELEASE/install/framework:$RELEASE/install/interfaces:/SDCARD/URAN/deps/nlohmann/usr:${CMAKE_PREFIX_PATH:-}"
colcon build --base-paths "$RELEASE/source/uran_ros2_adapter/src" \
  --build-base "$RELEASE/build/ros2" --install-base "$RELEASE/install/ros2" \
  --merge-install --packages-select uran_msgs uran_ros2_msgs uran_srvs \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DCMAKE_PREFIX_PATH="$CMAKE_PREFIX_PATH" \
  -Dnlohmann_json_DIR=/SDCARD/URAN/deps/nlohmann/usr/lib/cmake/nlohmann_json

# ROS Galactic's ament_cmake_export_targets template searches generated
# export files for the pre-CMake-3.30 `_expectedTarget` loop. CMake 3.30
# emits `_cmake_expected_target` instead, so add a harmless compatibility
# marker before configuring consumers of the generated message packages.
for export_file in "$RELEASE/install/ros2"/share/{uran_msgs,uran_ros2_msgs,uran_srvs}/cmake/*__rosidl_*Export.cmake; do
  [ -f "$export_file" ] || continue
  target_name="$(sed -n 's/^foreach(_cmake_expected_target IN ITEMS \(.*\))/\1/p' "$export_file" | head -n 1)"
  if [ -n "$target_name" ] && ! grep -q 'foreach(_expectedTarget ' "$export_file"; then
    sed -i "1i# foreach(_expectedTarget $target_name)" "$export_file"
  fi
done

export AMENT_PREFIX_PATH="$RELEASE/install/ros2:$AMENT_PREFIX_PATH"
export CMAKE_PREFIX_PATH="$RELEASE/install/ros2:$CMAKE_PREFIX_PATH"
colcon build --base-paths "$RELEASE/source/uran_ros2_adapter/src" \
  --build-base "$RELEASE/build/ros2" --install-base "$RELEASE/install/ros2" \
  --merge-install --packages-select uran_ros2_adapter \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DCMAKE_PREFIX_PATH="$CMAKE_PREFIX_PATH" \
  -Dnlohmann_json_DIR=/SDCARD/URAN/deps/nlohmann/usr/lib/cmake/nlohmann_json

mkdir -p "$RELEASE/state"
if [ -e "$ROOT/current" ] || [ -L "$ROOT/current" ]; then
  mv "$ROOT/current" "$ROOT/current.previous.$(date +%Y%m%d%H%M%S)"
fi
ln -s "$RELEASE" "$ROOT/current"
cp "$ROOT/config/secrets.env" "$ROOT/current/config/secrets.env"
chmod 600 "$ROOT/current/config/secrets.env"
echo "installed $ROOT/current"
