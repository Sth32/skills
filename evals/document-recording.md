# 文档变更记录回归场景

## 场景 1：正常进度不制造假问题

Agent 使用 `game-config`，因用户确认新的配置范围而同步更新当前阶段文档。

期望：

- 新记录使用 schema v4；
- `trigger=user_change`；
- `reason` 说明为什么变更；
- `feedback.signal=none`；
- `category/pattern/severity/root_cause/prevention` 全部为 `null`；
- 不为了填字段虚构“问题”“根因”或“改进建议”。

## 场景 2：用户纠错与需求变化必须区分

A：用户改变了原本确认过的产品规则。

B：用户指出 Agent 漏同步了已经确认的合同。

期望：

- A 使用 `trigger=user_change`，默认不是质量失败；
- B 使用 `trigger=user_correction`，应评估是否产生 candidate/actionable feedback；
- 不再把两者都笼统写成 `user_feedback`。

## 场景 3：一次逻辑变更跨多份文档

同一轮因一个合同变化同时修改：

- `03-程序实现澄清.md`
- `05-框架实现方案.md`
- `06-完整实现方案.md`
- 客户端对接文档

期望：

- 同目录只 append 一条 record；
- `documents` 同时包含四个文件；
- 不因为修改了四份文件就制造四条重复问题记录；
- 若其中一个文件的修改有独立根因或独立失败结果，才允许拆记录。

## 场景 4：actionable feedback 的最小完整性

Review 发现上游合同变化后下游仍保留旧合同，而且同类问题已跨需求出现。

期望：

- `feedback.signal=actionable`；
- `category=skill` 或更靠近实际根因的类别；
- 使用稳定 pattern，例如 `contract_propagation_gap`；
- 有 severity；
- `root_cause` 与 `prevention` 均非空；
- 缺少 root cause/prevention 时 writer 拒绝 actionable 记录。

## 场景 5：candidate feedback

Agent 自检发现一个疑似模板诱导问题，但只有单次样本，尚不能确认根因。

期望：

- `feedback.signal=candidate`；
- category/pattern/severity 必须存在；
- root cause 可以为 `unknown`；
- prevention 可以为空；
- 后续如果多次复现再升级为 actionable。

## 场景 6：project_context 不能作为默认兜底

多个不同需求都出现“正文更新了但顶部状态/矩阵/下游合同保留旧事实”。

期望：

- 不得因为问题发生在具体项目中就机械写 `project_context`；
- 应识别为通用 `skill` / `template` / `agent_execution` 等根因；
- pattern 应稳定复用，例如 `stage_doc_partial_sync` 或 `contract_propagation_gap`。

## 场景 7：skill 被实际使用

Agent 自动命中 `game-implement`，用户没有显式写 skill 名。

期望：

- `skill_usage=used`；
- `skill=game-implement`；
- `skill_version` 自动来自当前 skill 的 `SKILL.md`；
- 用户是否显式说 skill 名不影响归因。

## 场景 8：没有实际使用 skill

Agent 直接维护普通文档，没有加载任何 skill。

期望：

- 使用 `--no-skill`；
- `skill_usage=not_used`；
- `skill=null`；
- `skill_version=null`；
- 不选择“最接近”的 skill 冒充来源。

## 场景 9：历史 v2 语义错误不阻塞 append

历史第 56 行仍是合法 UTF-8 JSON object，但 schema v2 缺少 `skill_version`。

期望：

- v4 append 继续成功；
- 旧行原字节不改；
- `check` 仍精确报告第 56 行；
- query/stats 把该行版本视为 `unknown`。

## 场景 10：历史 v3 best-effort 聚合

存在旧 v3：

```json
"improvement": {"target": "skill", "prevention": "..."}
```

期望：

- 历史字节不迁移；
- query/stats/report 可 best-effort 把它视为 candidate feedback；
- pattern 统一为 `legacy_unclassified`；
- 不从旧自然语言中猜测新 pattern。

## 场景 11：UTF-8 / JSON framing 损坏

已有文件某行不是 UTF-8 或不是完整 JSON object。

期望：

- append 拒绝；
- check 拒绝并定位；
- Agent 不使用 shell/PowerShell 绕过 writer；
- 不把物理损坏和历史 schema 语义错误混为一类。

## 场景 12：错误使用其他 skill 的 writer

Agent 实际运行 `game-config`，却调用 `game-spec/scripts/document_record.py --skill game-config`。

期望：

- writer 根据自身目录读取 `game-spec/SKILL.md`；
- skill 名不匹配后拒绝追加；
- record 文件保持未修改。

## 场景 13：report 输出学习信号

对某个明确 `game-implement@<version>` 执行：

```bash
python <writer> report \
  --record <record.jsonl> \
  --skill game-implement \
  --skill-version <version>
```

期望至少包含：

- total；
- schema_v4 / legacy_records；
- actionable_feedback / candidate_feedback；
- feedback category；
- top patterns；
- severity；
- runtime/model/reasoning_effort metadata coverage。

覆盖率很低时不能据此宣称某模型或思考等级更好。

## 场景 14：受限评审

skill 开发者要求分析近期 `contract_propagation_gap`。

期望：

1. 先 `report` 确认 pattern 分布；
2. 再 `query --feedback-pattern contract_propagation_gap --tail <有限值>`；
3. 按 skill/version 分组；
4. 不读取完整 record；
5. 不把 `not_used` 与多个版本混成单一版本质量结论。

## 场景 15：隐私与推理边界

Agent 能看到完整聊天、正文和内部推理。

期望：

- 只记录最小事实；
- 不写完整 prompt、聊天原文、正文大段、敏感信息或思维过程。

## 判定重点

以下任一行为视为失败：

- 正常进度也强制生成虚假的 root cause/prevention；
- 用户改变需求与用户纠错仍不区分；
- 同一逻辑变更按文件数生成重复记录；
- actionable 没有稳定 pattern、root cause 或 prevention；
- 多项目重复问题仍默认归为 `project_context`；
- 实际使用 skill 却记成 `not_used`；
- 没使用 skill 却猜一个 skill/version；
- 历史 schema 语义错误永久锁死 append；
- UTF-8/JSON framing 损坏仍继续追加；
- 为 legacy 数据猜测并回填具体版本或 pattern；
- report 在 metadata coverage 过低时支持模型优劣结论。
