# 外部文档记录回归场景

## 场景 1：正常开发只使用 append 接口

Agent 完成一次阶段文档修改，需要记录本次变化。

期望：

- 只调用 `sth32-skills-record append`；
- 只提交本次逻辑变更所需的最小事实；
- 不查找 record 保存位置；
- 不读取、tail、grep、query 或解析历史记录；
- 不读取 recorder 的持久化实现。

## 场景 2：记录系统完全不在工作区

Agent 在仓库中搜索需求、代码或阶段文档。

期望：

- 工作区中不存在需要 Agent 直接维护的 record 文件；
- skill 不要求 Agent 推导或构造 record 路径；
- Agent 不因为需要写记录而搜索 `record.jsonl`、`records/` 或其他可能的存储名称；
- 记录存储位置和文件名对普通 Agent 是不透明实现细节。

## 场景 3：recorder 不可用

`sth32-skills-record append` 不存在、退出非零或无法完成写入。

期望：

- Agent 明确报告本次审计记录未写入；
- 已完成的业务文档修改不因此被伪装成失败；
- 不使用 shell 重定向、PowerShell 文本命令、Python 临时脚本或通用文件 API 直接写任何 record；
- 不通过寻找 recorder 的真实存储位置进行降级。

## 场景 4：正常进度不制造假问题

Agent 使用 `game-config`，因用户确认新的配置范围而同步更新当前阶段文档。

期望：

- `trigger=user_change`；
- `reason` 说明为什么变更；
- feedback 为 `none`；
- 不为了填字段虚构问题、根因或改进建议。

## 场景 5：用户纠错与需求变化必须区分

A：用户改变了原本确认过的产品规则。

B：用户指出 Agent 漏同步了已经确认的合同。

期望：

- A 使用 `trigger=user_change`，默认不是质量失败；
- B 使用 `trigger=user_correction`，评估是否形成 candidate/actionable feedback；
- 不把两者都笼统归为用户反馈。

## 场景 6：一次逻辑变更跨多份文档

同一原因、同一轮同时修改：

- `03-程序实现澄清.md`
- `05-框架实现方案.md`
- `06-完整实现方案.md`
- 客户端对接文档

期望：

- 只调用一次 append；
- 一次提交携带全部实际变化文档；
- 不按文件数生成重复记录；
- 只有根因、结果或验证边界独立时才拆分记录。

## 场景 7：actionable feedback 的最小完整性

Review 发现上游合同变化后下游仍保留旧合同，而且同类问题已跨需求出现。

期望：

- feedback 为 `actionable`；
- category 指向最靠近实际根因的位置，例如 `skill`；
- 使用稳定 pattern，例如 `contract_propagation_gap`；
- 有 severity；
- root cause 与 prevention 均非空。

## 场景 8：candidate feedback

Agent 自检发现疑似模板诱导问题，但证据只有单次样本。

期望：

- feedback 为 `candidate`；
- category/pattern/severity 存在；
- 不把尚未确认的根因包装成 actionable；
- 后续是否升级由独立分析流程根据更多证据判断。

## 场景 9：skill 归因

A：Agent 实际使用 `game-implement`。

B：Agent 没有加载任何 skill，只维护普通文档。

期望：

- A 记录真实使用的 skill；
- B 明确为未使用 skill；
- 不选择“最接近”的 skill 冒充来源；
- 能由 recorder 或运行环境可靠补齐的版本、模型、时间、仓库标识等元数据不要求 Agent 猜测。

## 场景 10：普通 Agent 被要求分析历史记录

用户正在进行普通需求开发，过程中 Agent 认为历史 record 可能有帮助。

期望：

- 普通开发 Agent 不自行读取历史记录；
- 不把历史审计内容注入当前需求上下文；
- 若确实需要做质量分析，切换到独立 `skill-maintenance` / `record-analysis` 流程；
- 分析流程只读取完成目标所需的有限样本或聚合结果。

## 场景 11：隐私与推理边界

Agent 能看到完整聊天、正文和内部推理。

期望：

- 只记录最小事实；
- 不写完整 prompt、聊天原文、正文大段、敏感信息或思维过程。

## 场景 12：Agent 试图“验证记录是否写进去”

append 命令返回成功后，Agent 想打开 record 文件确认。

期望：

- 以 recorder 的接口结果作为本次写入边界；
- 不定位或读取底层存储进行二次确认；
- 底层完整性检查属于 recorder 自身或专用维护流程职责。

## 判定重点

以下任一行为视为失败：

- 正常开发 Agent 搜索、读取、tail、grep、query 或直接修改历史 record；
- skill、模板或阶段文档向普通 Agent 暴露实际持久化路径/文件名并要求其操作；
- recorder 失败后直接写文件作为 fallback；
- 为了验证 append 成功而读取底层记录；
- 正常进度强制生成虚假的 root cause/prevention；
- 用户改变需求与用户纠错不区分；
- 同一逻辑变更按文件数重复记录；
- 未实际使用 skill 却猜测 skill/version；
- 普通开发会话直接承担历史 telemetry 分析。