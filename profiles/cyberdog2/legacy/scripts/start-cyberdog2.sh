#!/bin/bash
set -e

URAN_ROOT="${URAN_ROOT:-/SDCARD/URAN/current}"
if [ -f "$(dirname "$URAN_ROOT")/active.json" ]; then
  echo "managed URAN deployment detected; uran-supervisor owns the Runtime" >&2
  exit 2
fi
export URAN_ROOT
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export COLCON_TRACE="${COLCON_TRACE:-}"
if [ -f "$URAN_ROOT/config/secrets.env" ]; then
  set -a
  . "$URAN_ROOT/config/secrets.env"
  set +a
fi
. /etc/mi/ros2_env.conf
. /opt/ros2/galactic/setup.bash
. "$URAN_ROOT/install/ros2/setup.bash"
export URAN_INTERFACES_SCHEMA_DIR="$URAN_ROOT/source/uran_interfaces/schemas"
export LD_LIBRARY_PATH="$URAN_ROOT/install/framework/lib:$URAN_ROOT/install/interfaces/lib:$URAN_ROOT/install/ros2/lib:${LD_LIBRARY_PATH:-}"
exec ros2 run uran_ros2_adapter uran_runtime_node --ros-args \
  -p plugin_config:="$URAN_ROOT/source/uran_profiles/profiles/cyberdog2/runtime.yaml" \
  -p state_file:="$URAN_ROOT/state/runtime-state.json" \
  -p default_device_id:=device_001 \
  -p default_motion_component:=base \
  -p default_media_component:=media \
  -p snapshot_period_ms:=1000 \
  -p heartbeat_period_ms:=5000 \
  -p autostart:=true
