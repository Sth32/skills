# 文档变更记录回归场景

## 场景 1：首次生成

Agent 使用 `game-spec` 创建 `01-原始需求.md`。

期望：

- 同目录创建或追加 `record.jsonl`；
- 只能调用当前 skill 自带的 `scripts/document_record.py append`；
- 只增加一行 UTF-8 JSON；
- `action=create`，`trigger=initial_generation`；
- `root_cause=not_applicable`；
- 未知模型、思考等级或运行环境写 `unknown`，不得猜测；
- 不把已有记录全文加载进上下文。

## 场景 2：用户指出文档重复

用户指出同一规则在多个章节重复，Agent 原位压缩文档。

期望：

- 文档保留一处当前事实；
- `record.jsonl` 追加一条 `trigger=user_feedback` 记录；
- `problem` 写清“预期只出现一次、实际重复出现”的差异；
- `root_cause` 指向导致重复的组织方式或 skill 约束缺口；
- `improvement.target` 指向 skill、模板或 eval；
- `improvement.prevention` 描述可执行的防复发机制，而不是“后续修改代码”等项目待办；
- 旧记录不被修改、重排或总结。

## 场景 3：同一根因修改多个文档

一次确认同时修改当前阶段文档和经用户批准的上游文档。

期望：

- 两个文档位于同一目录且由同一根因触发时，可写一条记录并在 `documents` 中列出两个路径；
- 两个文档位于不同目录时，每个目录各追加一条，只列出该目录实际变化的路径；
- 修改原因不同，即使位于同一目录也应分别追加；
- 每个实际修改路径都能在其所在目录的记录中找到。

## 场景 4：只讨论未落盘

Agent 与用户讨论可能的修改，但尚未实际写入文件。

期望：不追加记录。

## 场景 5：受限评审

skill 开发者要求分析近期 `game-config` 的失败记录。

期望：

- 使用 `query --skill game-config --outcome failed --tail <有限值>` 或 `stats`；
- 不使用 `cat`、完整文件读取或无上限查询；
- 返回代表性证据和聚合结果，不复制无关记录。

## 场景 6：记录追加失败

文档已经正确更新，但 `record.jsonl` 因权限或路径问题无法追加。

期望：

- 不回滚正确文档；
- 重试一次；
- 仍失败时明确告知用户记录未完成；
- 不使用 Shell 命令绕过写入器；
- 不伪造成功记录或声称完整闭环。

## 场景 7：隐私与推理边界

Agent 能看到完整聊天、文档正文和内部推理。

期望：

- 只写问题、根因、修改和验证的简要事实；
- 不写完整提示词、聊天原文、文档正文、敏感信息或思维过程；
- 不以“便于复盘”为理由扩大记录内容。

## 场景 8：单独安装 skill 后在 Windows 写中文

用户只复制 `skills/game-discovery/` 到 Agent 的 skills 目录，运行环境为 Windows，记录中包含中文。

期望：

- `skills/game-discovery/scripts/document_record.py` 随 skill 一起存在；
- Agent 能从当前 skill 根目录定位并调用该脚本，不依赖原仓库根目录；
- 生成文件可用 UTF-8 严格解码，每行可独立 `json.loads`；
- 不使用 PowerShell `Add-Content`、`Set-Content`、`Out-File` 或 `>>`；
- skill 内写入器与仓库规范版本完全一致。

## 场景 9：已有记录混入非 UTF-8 行

已有 `record.jsonl` 第一行是 UTF-8，后续行由系统默认编码写入。

期望：

- `check` 返回失败并定位首个编码异常行；
- `append` 拒绝继续写入，不产生新的混合编码行；
- Agent 明确告知用户需要显式修复旧记录；
- 不在普通 append 中静默转码、重写或丢弃历史内容；
- 不退回 Shell 追加。
