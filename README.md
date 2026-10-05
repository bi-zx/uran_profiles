# URAN CyberDog2 profiles

This repository contains deployment assembly only. The CyberDog2 profile uses
the identity and network contract from the original `/SDCARD/uran_ws`; it does
not contain credentials or vendor source code. The temporary `/SDCARD/ARM`
workspace is deliberately not referenced.

The profile exposes the CyberDog2 `base` and SO101 `arm` motion components.
Communication and media remain service components. The arm worker reads its
serial device, calibration file, and LeRobot safety range from `runtime.yaml`.

## Layout

```text
profiles/cyberdog2/
├── profile.yaml
├── runtime.yaml
├── media.yaml
├── arm/uran_arm_calibration.yaml
├── services/uran-cyberdog2.service
└── checks/healthcheck.py
scripts/
├── validate_profile.py
└── render_runtime.py
```

`runtime.yaml` points to absolute paths below `/SDCARD/URAN/current` after
deployment. MQTT credentials are read from `config/secrets.env`, which is
created on the device from the original workspace and is never committed.

## Components and channels

The motion component is:

```text
device_001 / base / cyberdog2_motion
```

The media defaults preserve the old channel identifiers:

`front_cam`, `cyberdog_main`, `realsense_left`, `realsense_right`,
`realsense_depth`, `realsense_aligned`, and `realsense_aligned_rgb`.

The initial live profile uses the CyberDog image-transmission backend and the
main CyberDog image topic. RealSense channel declarations are retained in the
profile metadata and are enabled only after their source-specific acceptance
check passes.

## Validation

Run the standard-library profile checks before deployment:

```bash
python3 scripts/validate_profile.py profiles/cyberdog2
```

The target launcher performs the same check, verifies ROS and vendor topics,
and starts the new runtime without stopping the old workspace.
