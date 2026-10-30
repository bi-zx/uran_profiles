# URAN Profiles

本仓库管理不同机器人产品的装配、参数覆盖、发行规格和验收检查。每个产品放在 `profiles/<profile_id>/`，产品名称、设备路径和厂商环境只属于对应 Profile。

通用框架、bootstrap、授权和部署事务由 `uran_framework` 提供；运动控制、媒体后端、设备驱动和校准算法由 `uran_plugins` 提供。本仓库消费这些能力，不在通用工具中实现具体机器人的逻辑。

## 目录职责

```text
uran_profiles/
├── profiles/                      # 各产品独立装配
│   └── cyberdog2/                  # 当前已有的一个产品 Profile
│       ├── profile.yaml
│       ├── runtime.yaml
│       ├── arm/                    # 标定模板；现场标定另行管理
│       ├── checks/                 # 产品专用检查
│       ├── services/               # 产品服务描述
│       ├── legacy/scripts/         # 旧源码部署的兼容入口
│       └── README.md
├── scripts/                       # 与机器人型号无关的发行端工具
│   ├── build_release.py
│   ├── validate_profile.py
│   └── render_runtime.py
├── templates/
│   └── managed-release/           # 通用受控发行模板
└── tests/                         # 通用装配工具验证
```

增加机器人时创建新的 `profiles/<profile_id>/`，选择已有插件或在插件仓库添加后端，再编写该产品的参数、检查和发行规格。顶层 `scripts/` 不增加 `<robot>-worker`、专用安装器、厂商环境加载或固定设备身份。

## 通用工具

```bash
python3 scripts/validate_profile.py profiles/<profile_id>
python3 scripts/render_runtime.py profiles/<profile_id> /path/to/runtime.yaml
python3 scripts/assemble_release.py --help
python3 scripts/build_release.py --help
```

`assemble_release.py` 在发行端把 Profile、已安装的 framework SDK 和插件 wheel 组装成受控发行的输入目录：复制 SDK 运行文件（与 bootstrap seed 相同），用当前解释器从锁定的 wheelhouse 离线安装 wheel 到 `python/`，按插件 wheel 的 console script 生成 `bin/` 启动入口（Profile `bin/` 中同名文件优先），复制 `checks/` 与 `runtime.json`（到 `config/runtime.json`），并生成带包来源与摘要的发行规格。它拒绝 `.git`、`secrets.env`、`device.json`、私钥等文件，检查装配引用的启动入口和检查命令确实存在且可执行。

必须在与目标完全一致的环境中运行（架构、发行版、libc，以及运行脚本的 Python 主次版本）：`build-release` 会在发行端执行与设备相同的平台检查。

```bash
python3 scripts/assemble_release.py profiles/<profile_id> \
  --sdk-prefix /opt/uran-sdk --sdk-version 2.1.0 --sdk-ref '<framework 版本或 commit>' \
  --wheel dist/uran-<product>-plugin-<version>-py3-none-any.whl --wheelhouse /srv/wheelhouse \
  --release-id <profile_id>-<version> --output /srv/uran-release/assembly --spec-out /srv/uran-release/release-spec.json
python3 scripts/build_release.py /srv/uran-release/assembly --spec /srv/uran-release/release-spec.json \
  --url https://artifacts.example.com/<profile_id>-<version>.tar.gz \
  --private-key publisher.key.pem --key-id publisher-2026 --output /srv/uran-release/output/<profile_id>-<version>.tar.gz
```

`validate_profile.py` 只检查装配结构、标识唯一性和引用关系，不要求固定机器人型号、`device_id`、底盘或机械臂。安装 PyYAML 后可校验 YAML；JSON 格式可仅用标准库校验。产品有额外约束时，在自己的 `checks/` 中实现并单独调用。

`render_runtime.py` 用于复制旧格式的 `runtime.yaml`，不改写设备参数。`build_release.py` 在发行端调用安装后的 `uran-deploy`，将已安装制品装配成签名发行物。新设备使用 [managed-release 模板](templates/managed-release/README.md)，按 framework 的 [受控部署说明](../uran_framework/docs/受控部署与Bootstrap.md)安装统一 bootstrap，再经 Core 提交发行任务。

worker 可执行入口来自对应插件 wheel 的 console script，由 `assemble_release.py` 生成，不由本仓库为每个产品复制一套公共 worker。产品需要额外启动环境时，包装入口放在自己 Profile 的 `bin/` 中，与生成的入口同名即可替换它。

## 现有产品

[CyberDog2 Profile](profiles/cyberdog2/README.md)保留现有设备的装配和旧源码部署兼容脚本。其 `/SDCARD` 路径、ROS Galactic 环境和厂商配置不作为其他 Profile 的默认值。旧安装器检测到受控部署的 `active.json` 后会拒绝覆盖或重复启动。

设备凭据与现场标定不得打入公共发行物。受控部署使用设备配置和持久化数据目录引用；旧 Profile 的现场配置方式以其产品说明为准。
