# CyberDog2 Profile

这是 URAN Profiles 中的一个产品装配。以下路径均相对 `uran_profiles` 仓库；通用仓库说明见[仓库 README](../../README.md)。新的受控部署入口见 [managed-release 模板](../../templates/managed-release/README.md)和 `scripts/build_release.py`。旧源码部署脚本集中在本 Profile 的 `legacy/scripts/`，检测到监督进程的 `active.json` 后会拒绝覆盖或重复启动。

This profile contains deployment assembly only. The CyberDog2 profile uses
the identity and network contract from the original `/SDCARD/uran_ws`; it does
not contain credentials or vendor source code. The temporary `/SDCARD/ARM`
workspace is deliberately not referenced.

The profile exposes the CyberDog2 `base` and SO101 `arm` motion components.
Communication and media remain service instances. The arm worker reads its
serial device, calibration file, and LeRobot safety range from `runtime.yaml`.

## Layout

```text
profiles/cyberdog2/
├── profile.yaml
├── runtime.yaml
├── arm/uran_arm_calibration.yaml   # template;现场 JSON 不入库
├── services/uran-cyberdog2.service
├── checks/
│   ├── healthcheck.py
│   └── validate_legacy.py          # 产品固定身份、base/arm 检查
├── legacy/scripts/                # 旧源码部署兼容入口
└── README.md
```

`runtime.yaml` points to absolute paths below `/SDCARD/URAN/current` after
deployment. MQTT credentials are read from `config/secrets.env`, which is
created on the device from the original workspace and is never committed.

The arm uses the persistent USB identity path
`/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B79017505-if00`. Media keeps the original STUN, TURN and
video source declarations directly in `runtime.yaml`; it does not read another
workspace at runtime. The profile preserves the original channel metadata (absolute ROS topics
remain absolute; relative CyberDog topics remain relative).
The current CyberDog2 WebRTC bridge delegates ICE to the vendor
`image_transmission` node, so the inline ICE settings are retained for
software backends but do not change that node's ICE servers. Channel metadata alone does not activate independent
camera subscriptions; the current worker still uses its configured main
CyberDog camera source.

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
python3 profiles/cyberdog2/checks/validate_legacy.py profiles/cyberdog2
```

通用校验器检查装配引用；`validate_legacy.py` 负责这个旧产品固定的身份、底盘和机械臂要求。`healthcheck.py` 是产品现场 ROS/Topic 诊断，另行执行。

旧安装器入口为 `profiles/cyberdog2/legacy/scripts/install_on_cyberdog2.sh`，只保留给尚未切换的源码部署设备。它把同目录下的启动包装复制到设备 `runtime/bin/`，因此现有服务描述中的启动路径不变。这些脚本不是通用 bootstrap，也不用于新受控发行物。

SO101 的 LeRobot 方式校准实现在插件包 `uran_so101_plugin.calibrate_lerobot`，随插件提供 `uran-so101-calibrate-lerobot` 入口，显式指定 `--port` 和 `--output`。本 Profile 的 `legacy/scripts/uran-so101-calibrate` 只提供旧设备的默认参数，不包含校准算法。已有设备的 `runtime/bin/uran-so101-calibrate` 使用方式保持一致；安装插件后也可直接执行：

```bash
uran-so101-calibrate-lerobot \
  --port /dev/serial/by-id/usb-1a86_USB_Single_Serial_5B79017505-if00 \
  --output /path/to/device-data/so101_follower_arm.json
```

## SO101 无 Placo 控制

CyberDog2 profile 使用 20 Hz 的位置/姿态 DLS 控制器、0.2 s 速度命令看门狗和 STL 派生自碰撞包络。直接读取已完成的 `arm/so101_follower_arm.json`；不再叠加其他机械臂的 COM9 标定。算法、诊断方法和验证边界见相邻仓库 `uran_plugins/motion/so101/README.md`。

`component.arm.control.status.motion_ready` 与 `readiness_error` 可判断起始关节姿态是否满足实际生效限位。默认是 URDF 与标定交集；当前 profile 仅将 `shoulder_lift` 配置为使用已完成标定的约 −114.77°～114.77°范围。服务 active 不能代替此检查。发送普通速度控制时，未使用的 `target_roll/pitch/yaw` 应设为 `null`。首次运动前需要确认供电稳定和起始姿态合法。

电压偶发告警支持自动恢复：`voltage_auto_recovery: true`，每 0.5 秒读取六轴，连续 3 次无告警后恢复接收新指令。恢复不执行旧目标或自动开启扭矩；急停、过热/过载、串口错误等不自动解除。进度与累计恢复次数见 `component.arm.control.status.voltage_recovery`。
