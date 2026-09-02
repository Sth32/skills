# 文档变更记录

## 目的

记录系统用于给后续 skill 维护提供低成本质量信号，不是项目文档，也不是普通开发 Agent 的上下文来源。

## 结构

每个 skill 自带完整的 `scripts/document_record.py`。Agent 只执行它的 `append` 接口；写入器把记录保存到仓库外的用户级目录。默认存储根位于 `~/.sth32_skills`，具体文件组织属于写入器实现细节。

普通开发流程禁止读取历史记录。需要分析历史 feedback 时，应使用独立的 skill-maintenance / record-analysis 流程，而不是把记录注入正在实现需求的 Agent 上下文。

## 写入规则

- 每次逻辑文档变更完成后追加一次；同一原因、同一轮、同一原子变更合并记录。
- `documents` 只写仓库相对路径，不记录本机绝对路径。
- 正常进度使用 `feedback.signal=none`；只有出现值得学习的偏差才使用 `candidate` / `actionable`。
- `user_change` 表示用户改变需求；`user_correction` 表示用户指出 Agent 或文档错误。
- 只记录最小事实，不写完整 prompt、聊天原文、正文大段、敏感信息或内部思维过程。
- 写入失败时报告失败，不得直接操作存储文件绕过脚本。

## Agent 边界

普通开发 Agent 不读取、搜索或修改 `document_record.py` 源码，不定位或读取历史记录，不使用 `cat` / `tail` / `grep` / 通用文件读取 API 检查记录。写入器只提供 append，不提供 query/report/check，从接口层减少历史记录进入上下文的机会。

## 维护边界

只有在明确维护 recorder 本身或进行 skill 质量分析时，才允许专门流程读取实现或历史记录；这类流程与正常游戏需求开发隔离。
