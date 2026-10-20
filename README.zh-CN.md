# Not yet dead

**模型停了，工作还可以接下去。**

[English](README.md) · [技能说明](SKILL.md) · [命令参考](references/cli.md) · [MIT 许可证](LICENSE)

Not yet dead 将已经保存的任务进展、最新方向和真实产物，整理成下一位 agent
可以核验的交接包。适用于主动暂停、异常退出、切换模型、换会话或迁移到其他平台。

它保留目标、决策、已完成、未完成、未知、证据和下一步。未保存的内部状态无法恢复。

## 开始使用

需要 **Python 3.10 或以上**。文件交接核心只用 Python 标准库，无需安装第三方依赖、
提供 API 密钥或运行 Hermes 桌面。

在仓库目录执行：

```sh
python -B scripts/not_yet_dead.py doctor
python -B scripts/not_yet_dead.py resume --workspace examples/workspace
python -B scripts/demo.py
```

示例使用合成资料，在系统临时目录中完成导出、验证和当前文件差异比较。

## 安装到其他 agent

把整个仓库目录复制或克隆到目标 agent 支持的技能目录，目录名使用 `not-yet-dead`。
保留 `SKILL.md`、`scripts/`、`lib/` 和 `references/`，让 agent 读取技能说明，
再用实际安装路径运行 `doctor`。

目标 agent 需要能够读取文件和执行 Python。只有聊天与附件能力时，可以阅读交接材料，
但生成和校验交接包需要另外提供执行环境。各平台技能加载方式仍需在目标环境中验证。
详见 [agent 接入说明](references/agents.md)。

公开项目名是 **Not yet dead**，原本的本机技能名是 **ninnin**。
内部模块与 v1 交接格式保持兼容。克隆公开仓库不会自动修改或重命名本机已有的 ninnin。

## 当前能力

| 命令 | 作用 |
| --- | --- |
| `doctor` | 检查 Python、核心文件和本地入口。 |
| `resume` | 只读当前状态、恢复说明和批准记录；可比对旧包与当前产物。 |
| `extract` | 从已保存的 JSON 快照和检查点导出交接包。 |
| `verify` | 校验结构、文件清单、大小和 SHA-256。 |
| `export` | 从兼容的 ninnin 工作台数据根目录导出指定任务。 |
| `status` | 列出兼容工作台数据库中的房间。 |

`resume` 不会自动继续任务。`export`、`status` 沿用 Store 构造器，可能初始化数据库并
设置 WAL 模式，只应对明确选择的兼容工作台目录使用。普通文件项目使用 `resume`、`extract`。

导出示例：

```sh
python -B scripts/not_yet_dead.py extract --snapshot examples/snapshot.json --checkpoint examples/checkpoint.json --workspace examples/workspace --out /path/to/new-handoff
python -B scripts/not_yet_dead.py verify /path/to/new-handoff
```

把示例路径替换为本机真实路径，输出目录必须是新目录。生成内容包括可读交接说明、清单、
必要产物快照和公开证据记录。旧包保留截止点，当前文件后续变化会标记为一致、变化或缺失，
不会自动拿旧文件覆盖新进展。输入格式见 [输入说明](references/inputs.md)。

## 能力边界

- 不会后台自动监听模型、自动保存检查点、恢复隐藏推理或自动压缩上下文。
- 交接包不提供新的执行许可；接手依据当前用户指令和已有批准范围。
- 对常见敏感文件名、凭据模式及私有事件有检查和过滤，分享前仍需核对实际内容。
- 自动新建会话、投递和确认接收需要目标宿主的接口。生成或验证包成功不等于实际接手完成。
- 哈希证明文件一致，不证明结论正确。文件测试通过不等于所有 agent 的接续效果都已验证。

## 本地测试

```sh
python -B -m unittest discover -s tests -t . -v
```

测试只使用临时合成资料，不调用真实模型。仓库配有 Windows、Linux、macOS 的 CI 配置，
实际远端运行结果以 GitHub Actions 为准。

采用 [MIT 许可证](LICENSE)。来源与兼容说明见 [NOTICE.md](NOTICE.md)。
