# 文档变更记录机制

## 目标

`record.jsonl` 不是阶段状态文档，而是用于捕获 Agent 文档变更与真实失误信号的审计数据。它的用途是：

- 追踪文档何时、为什么被修改；
- 区分正常推进与值得学习的偏差；
- 为 skill、模板、eval、工具和 Agent 执行规则提供可聚合证据；
- 按 skill/version 观察改进是否减少同类问题。

当前需求、方案、实现状态仍只存在于对应阶段权威文档中。

## 文件位置与写入粒度

每个阶段文档目录维护一份：

```text
<document-directory>/record.jsonl
```

同一目录多个阶段文档共用该文件，通过 `documents` 区分。

**一条 record 对应一次逻辑上的原子变更，不对应一份文件。**

同一原因、同一轮、同一目录内，为了完成同一个结构性修正同时更新 `01/03/05/06` 时：

- 只追加一条记录；
- `documents` 列出全部实际变化文件；
- 只有根因、验证边界或结果不同，才拆成多条记录。

这避免把一次修正膨胀成多条重复日志，也让“记录数”更接近“决策/失误/修复次数”。

## Schema v4

新记录使用 `schema_version=4`。

核心字段：

| 字段 | 含义 |
|---|---|
| `schema_version` | 固定为 `4` |
| `timestamp` | 带时区 ISO 8601 时间 |
| `skill_usage` | `used` / `not_used` |
| `skill` | 实际使用的 skill；无 skill 时为 `null` |
| `skill_version` | 实际 skill 版本；无 skill 时为 `null` |
| `runtime` | Agent 运行环境，未知写 `unknown` |
| `model` | 实际模型名，未知写 `unknown` |
| `reasoning_effort` | 实际思考等级，未知写 `unknown` |
| `action` | `create` / `update` / `delete` / `rename` |
| `documents` | 本次逻辑变更实际涉及的文档路径数组 |
| `trigger` | 触发原因 |
| `reason` | 为什么发生本次变更 |
| `change_summary` | 实际改了什么 |
| `validation` | 验证状态与最小证据 |
| `outcome` | `success` / `partial` / `failed` |
| `feedback` | 是否产生可用于改进的学习信号 |
| `commit` | 可选提交标识 |

v4 不再要求每条正常进度都填写 `problem/root_cause/improvement`。**正常推进不是问题，不得为了 schema 完整性虚构根因。**

## trigger：区分需求变化与 Agent 错误

新增两类必须区分：

- `user_change`：用户改变、补充或重新确认需求；不是质量失败。
- `user_correction`：用户指出 Agent、文档或实现已有错误/遗漏；属于质量信号候选。

其他触发：

- `initial_generation`
- `self_check`
- `review_feedback`
- `test_failure`
- `code_change`
- `upstream_change`
- `other`

`user_feedback` 仅作为旧调用兼容保留，新记录不应继续把所有用户输入都塞入这一类。

## feedback：把审计日志变成学习数据

### 1. `signal=none`

用于正常进度、需求自然变化、无可泛化缺陷的同步修改。

```json
"feedback": {
  "signal": "none",
  "category": null,
  "pattern": null,
  "severity": null,
  "root_cause": null,
  "prevention": null
}
```

此时不得硬编 root cause 或 prevention。

### 2. `signal=candidate`

已经出现值得关注的偏差，但证据还不足以确认是通用规则缺陷。

必须填写：

- `category`
- 稳定的 snake_case `pattern`
- `severity`

`root_cause` 可以仍是 `unknown`，`prevention` 可以为空。

### 3. `signal=actionable`

已经能定位根因，并且可以提出明确防复发措施。

除 candidate 字段外，必须填写：

- `root_cause`
- `prevention`

推荐在以下情况使用：

- 同一类问题跨需求重复出现；
- `game-review` 发现本应由更早阶段 skill 防住的通用缺陷；
- 用户明确指出 Agent 的流程性错误；
- self-check 发现当前 skill 的规则不足导致系统性遗漏；
- 模板结构持续诱导错误或重复信息。

## feedback.category

允许值：

- `skill`：skill 流程、门禁、边界或判断规则不足；
- `template`：模板结构诱导遗漏、冲突或重复；
- `eval`：缺少能阻止回归的场景；
- `tooling`：写入器、验证器、CI 或辅助脚本问题；
- `agent_execution`：规则本身已足够明确，但 Agent 没有执行；
- `project_context`：问题确实依赖单一项目缺失/错误事实。

**不要把 `project_context` 当默认兜底。**

若相同模式在不同需求出现，或 review 发现的是通用失效模型，应优先归到最靠近根因的 `skill/template/eval/tooling/agent_execution`。

## pattern 规则

`pattern` 用于跨记录聚合，必须是稳定、可复用的 snake_case key，而不是一句自然语言。

推荐示例：

```text
stage_doc_partial_sync
contract_propagation_gap
client_rpc_reachability_missing
runtime_config_not_consumed
authorization_execution_identity_mismatch
stale_async_callback_overwrite
lifecycle_terminal_state_gap
rollback_not_executable
```

同一根因优先复用既有 pattern，不要每次换同义词。

## skill/version 归因

### 实际使用了 skill

调用当前 skill 自带写入器：

```bash
python <skill-root>/scripts/document_record.py append \
  --skill <skill-name> ...
```

要求：

- `skill_usage=used`；
- `skill` 等于当前实际加载/执行的 skill；
- `skill_version` 从该 skill 自己的 `SKILL.md -> metadata.version` 自动读取；
- Agent 不手填、不猜测版本；
- 用户是否显式写出 skill 名称不影响归因。

### 实际没有使用 skill

使用：

```bash
python <writer> append ... --no-skill
```

得到：

```json
"skill_usage": "not_used",
"skill": null,
"skill_version": null
```

不得挑一个“最像”的 skill 冒充来源。

## 示例

正常结构同步：

```bash
python <writer> append \
  --skill game-tech-clarify \
  --record docs/requirements/foo/record.jsonl \
  --action update \
  --document docs/requirements/foo/03-程序实现澄清.md \
  --document docs/requirements/foo/05-框架实现方案.md \
  --trigger user_change \
  --reason "用户确认合同范围变化，需要同步依赖文档" \
  --change "更新通信合同及框架引用" \
  --validation-status passed \
  --validation "影响扫描未发现旧合同残留" \
  --outcome success
```

通用缺陷：

```bash
python <writer> append \
  --skill game-implement \
  --record docs/requirements/foo/record.jsonl \
  --action update \
  --document docs/requirements/foo/06-完整实现方案.md \
  --trigger user_correction \
  --reason "用户指出上游合同变化后 06 仍保留旧语义" \
  --change "收敛旧合同引用并补影响扫描" \
  --validation-status passed \
  --outcome success \
  --feedback-signal actionable \
  --feedback-category skill \
  --feedback-pattern contract_propagation_gap \
  --feedback-severity high \
  --root-cause "结构性变化只更新了局部文档，没有执行依赖传播检查" \
  --prevention "把结构性变更影响传播设为所有阶段的公共门禁"
```

## append 与 check 的职责

append 只阻止存储层损坏：

- 文件不是普通文件；
- 非 UTF-8；
- 某行不是完整 JSON；
- 某行不是 JSON object。

历史 schema 字段缺失或语义错误不阻塞后续独立追加。

`check` 对所有记录做严格 schema 检查，负责报告历史非法 v2/v3/v4 记录。

## 历史兼容

历史记录保持原字节，不迁移、不猜测：

- v1 缺版本 → 查询统计视为 `unknown`；
- 合法 v2 保留版本；
- 非法 v2 缺版本 → `check` 报错，但 append 仍允许；
- v3 保留原 `problem/root_cause/improvement`；查询/统计可 best-effort 映射为 feedback candidate；
- v3 `improvement.target != none` 在聚合时使用 `pattern=legacy_unclassified`，只作为历史候选，不冒充精确新 pattern；
- v3/v4 no-skill 统一统计为 `none@not_applicable`。

## 查询、统计与 report

禁止 Agent `cat` 或完整读取 `record.jsonl`。

允许：

```bash
python <writer> query --record <path> --tail 20
python <writer> stats --record <path>
python <writer> report --record <path> --skill game-implement --skill-version 0.1.11
```

`report` 输出：

- actionable/candidate 数量；
- category 分布；
- 高频 pattern；
- severity 分布；
- v4 与 legacy 样本量；
- `runtime/model/reasoning_effort` 的已知值覆盖率。

模型、思考等级或运行环境覆盖率低时，**不得据此做模型优劣结论**。

## 从记录到 skill 改进

推荐顺序：

1. 用 `report` 查看某个 `skill@version` 的 actionable/candidate 与高频 pattern；
2. 对高频 pattern 用 `query --feedback-pattern <pattern> --tail <有限值>` 抽案例；
3. 判断最靠近根因的位置：skill、template、eval、tooling、agent_execution 或 project_context；
4. 修改根因位置，而不是只在 review 末端打补丁；
5. 对通用问题补 regression eval；
6. 后续版本中同 pattern 明显下降，才算改进有效。

## 隐私与上下文边界

record 只记录最小事实，不得写：

- 完整提示词；
- 聊天原文；
- 文档正文大段复制；
- 用户敏感信息；
- 内部思维过程。

## 写入限制

写入器使用 UTF-8 无 BOM、二进制 `O_APPEND` 单次追加完整 JSON 行。

禁止：

- `>` / `>>` / `echo`；
- PowerShell `Add-Content` / `Set-Content` / `Out-File`；
- 依赖系统默认编码的通用文本写入；
- writer 失败后绕过 writer 直接修改 `record.jsonl`。
