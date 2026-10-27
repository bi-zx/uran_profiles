# 受控发行装配

此模板用于新部署器。`runtime.json` 是空产品装配；Core 管理 worker 和云端连接由设备管理底座注入，不在产品包中重复声明。

发行端先把安装后的 SDK、插件 wheel/二进制、资源和 worker 入口组成一个目录，再使用 `scripts/build_release.py` 调用安装后的 `uran-deploy build-release`。发行规格参考 framework 的 `config/deployment/release-spec.example.json`；包版本、来源和摘要必须填写真实值。

路径使用 `${release}` 引用当前不可变发行目录、`${device_id}` 引用设备身份、`${data}` 引用可备份的运行状态、`${shared}` 引用现场持久化数据。标定文件例如 `${shared}/calibration/so101_follower_arm.json`，不打入发行包。插件实例不能使用保留名称 `uran_management`、`uran_cloud`、`uran_runtime`。

ROS 和厂商环境可由已签名发行物中的 worker 启动入口装载。宿主使用管理底座支持的原生 Core CLI；具体 ROS 驱动仍放在插件/适配器仓库。硬件产品必须提供停机前的 `preflight` 检查和启动后的 `checks`，确保停机条件、安全状态、设备权限和业务健康满足要求。

使用固定路径、源码依赖或专用安装脚本的旧 Profile 不能直接当作此格式安装。现有设备切换前需要生成可迁移的产品发行物、迁出身份和标定、停止旧服务，并完成该产品的停机/回退与硬件验收。

完整安装、授权和恢复说明以 framework 的 `docs/受控部署与Bootstrap.md` 为准。
