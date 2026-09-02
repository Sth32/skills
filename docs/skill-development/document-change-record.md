# 文档变更记录机制

## 目标

文档变更记录用于捕获 Agent 修改文档时的审计事实和可学习失误信号，为后续 skill、模板、eval、工具和 Agent 规则改进提供证据。

它不是阶段状态文档，也不是项目知识库。当前需求、方案、实现状态只存在于对应权威文档中。

## 核心边界

记录系统是 **仓库外部 telemetry 基础设施**。

正常开发 Agent：

- 只提交本次记录；
- 不读取历史记录；
- 不搜索记录文件；
- 不定位记录存储；
- 不检查 recorder 实现；
- 不把历史记录注入当前任务上下文。

Agent 只依赖一个稳定命令接口：

```bash
sth32-skills-record append ...
```

存储路径、文件名、编码、schema 的持久化表示和历史查询能力都属于 recorder 内部实现，不在 skills、阶段文档和普通 Agent 使用说明中暴露。

如果命令不存在或执行失败，Agent 应明确报告“本次记录未写入”，但继续保留本次业务修改结果；禁止用 shell 重定向、通用文本 API 或直接文件操作绕过 recorder。

## 写入粒度

一条 record 对应一次逻辑上的原子变更，不对应一份文件。

同一原因、同一轮，为完成同一结构性修正同时更新多份文档时：

- 只提交一次记录；
- 携带全部实际变化文档；
- 只有根因、结果或验证边界不同才拆分。

## Agent 需要提交的信息

Recorder 接口应至少接受：

- 当前实际使用的 skill；
- action：`create` / `update` / `delete` / `rename`；
- documents：本次实际变化文档；
- trigger；
- reason；
- change summary；
- validation；
- outcome；
- 可选 feedback。

时间、运行环境、模型、思考等级、skill version、仓库与提交标识等能够由 recorder 或运行环境可靠获取的信息，应由 recorder 自动补齐，不要求 Agent 猜测或重复填写。

## trigger

必须区分：

- `user_change`：用户改变、补充或重新确认需求；不是质量失败；
- `user_correction`：用户指出 Agent、文档或实现已有错误/遗漏；属于质量信号候选。

其他 trigger 可以由 recorder contract 继续维护，但不得把所有用户输入统一记成质量失败。

## feedback

正常推进不需要制造问题。

- 无可泛化缺陷：`signal=none`；
- 已发现值得关注但证据不足：`candidate`；
- 已定位根因且能形成防复发措施：`actionable`。

可泛化问题应优先归因到最靠近根因的位置，例如：

- `skill`
- `template`
- `eval`
- `tooling`
- `agent_execution`
- `project_context`

`project_context` 只用于确实依赖单一项目事实的问题，不作为默认兜底。

`pattern` 应使用稳定、可复用的 snake_case key，便于跨记录聚合。

## 查询边界

普通开发 Agent 没有读取历史记录的职责。

需要根据历史记录改进 skills 时，使用独立的 `skill-maintenance` / `record-analysis` 流程。该流程与正常需求开发上下文隔离，只读取完成分析所需的有限样本或聚合结果。

这条边界的目的不是保密，而是防止历史审计数据污染当前任务上下文和决策。

## 隐私与上下文限制

记录只保存最小事实，不得写入：

- 完整提示词；
- 聊天原文；
- 文档正文大段复制；
- 用户敏感信息；
- 内部思维过程。

## 设计原则

记录系统应满足：

1. **append-only**：正常 Agent 只能追加本次事件；
2. **location opaque**：Agent 不需要知道记录保存在哪里；
3. **implementation opaque**：Agent 不需要知道 recorder 如何持久化；
4. **workspace isolated**：记录不出现在项目工作区和默认搜索空间；
5. **failure explicit**：记录失败可以被发现，但不能诱导 Agent 绕过接口；
6. **analysis separated**：历史记录分析与正常开发会话分离。

最终目标是让 record 成为低干扰的质量 telemetry，而不是另一个 Agent 会主动探索的项目文档。