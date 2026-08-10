# 文档变更记录回归场景

## 场景 1：skill 被实际使用

Agent 使用 `game-spec` 创建 `01-原始需求.md`。用户可以显式要求，也可以由 Agent 根据 skill 描述自动命中。

期望：

- 同目录创建或追加 `record.jsonl`；
- 使用当前 skill 自带的 `scripts/document_record.py append --skill game-spec ...`；
- 新记录为 `schema_version=3`；
- `skill_usage=used`；
- `skill=game-spec`；
- `skill_version` 自动等于当前 `game-spec/SKILL.md` 的 `metadata.version`；
- 用户是否显式写出 skill 名称不影响归因；
- Agent 不手填、猜测或缓存 `skill_version`。

## 场景 2：没有实际使用任何 skill

Agent 直接处理一个普通文档修改，没有加载或执行任何 skill。

期望：

- 仍可记录该次变更；
- 使用 writer 的 `--no-skill` 模式；
- `schema_version=3`；
- `skill_usage=not_used`；
- `skill=null`；
- `skill_version=null`；
- 不得选择一个“最接近”的已安装 skill 代替；
- 查询/统计将其归入 `skill=none`、`skill_version=not_applicable`。

## 场景 3：自动命中 skill，但用户没说 skill 名

用户只描述任务，Agent 自动加载 `game-implement` 并按其流程执行。

期望：

- 这是实际 skill 使用，不能记成 `not_used`；
- `skill_usage=used`；
- `skill=game-implement`；
- `skill_version` 来自该 skill 自身 `SKILL.md`；
- “用户未显式声明 skill”不得作为缺少版本的理由。

## 场景 4：历史 schema v2 缺少 skill_version

`record.jsonl` 第 56 行仍是有效 UTF-8 JSON object，但声明 `schema_version=2` 且缺少 `skill_version`。

随后产生一条新的合法记录。

期望：

- `append` 不因第 56 行的历史字段语义错误而拒绝新记录；
- 新记录作为下一行正常追加，旧第 56 行原字节不改；
- `check` 仍返回失败，并准确指出第 56 行缺少合法 `skill_version`；
- `query` / `stats` 保留第 56 行为 best-effort 历史数据，并把其版本视为 `unknown`；
- 不要求先人工修第 56 行才能继续记录；
- 不静默猜测第 56 行当时的 skill 版本。

## 场景 5：历史文件存在 UTF-8 / JSON framing 损坏

已有 `record.jsonl` 某一行不是 UTF-8，或不是完整 JSON object。

期望：

- `append` 拒绝继续写入；
- `check` 同样失败并定位首个损坏行；
- Agent 明确告知用户需要修复存储层损坏；
- 不使用 Shell/PowerShell 绕过；
- 不把“历史 schema 字段缺失”和“JSONL 物理损坏”混为同一类错误。

## 场景 6：错误使用其他 skill 的写入器

Agent 实际运行 `game-config`，却调用 `game-spec/scripts/document_record.py append --skill game-config ...`。

期望：

- 写入器从自身路径读取 `game-spec/SKILL.md`；
- 发现 `--skill=game-config` 与自身名称不一致后拒绝追加；
- 不允许调用者传 `skill_version` 覆盖；
- Agent 改为调用 `game-config` 自带写入器。

## 场景 7：当前 skill 缺少合法版本

Agent 实际使用某 skill，但其 `SKILL.md -> metadata.version` 缺失或不是 `x.y.z`。

期望：

- `skill_usage=used` 的记录拒绝追加；
- 不写 `unknown` 冒充具体版本；
- 不切换到 `--no-skill` 来掩盖“其实使用了 skill”；
- 先修复该 skill 的元数据，再恢复 skill-attributed 记录。

## 场景 8：schema v1 与 v2 历史兼容

同一文件存在：

- schema v1，无 `skill_version`；
- 合法 schema v2，有具体版本；
- 非法 schema v2，缺少版本；
- schema v3 的 skill-attributed 新记录；
- schema v3 的 no-skill 新记录。

期望：

- 历史字节不被重写；
- v1 与非法 v2 的版本统计为 `unknown`；
- 合法 v2 保留其原版本；
- v3 skill 记录按具体版本统计；
- v3 no-skill 统计为 `none@not_applicable`；
- 评价某个 skill 版本时排除 `not_used` 与 `unknown` 样本。

## 场景 9：受限评审

skill 开发者要求分析近期 `game-config` 的失败记录。

期望：

- 先用 `stats` 查看 `skill_usage`、`skill_version` 和 `skill_release` 分布；
- 对明确版本使用 `query --skill game-config --skill-version <version> --outcome failed --tail <有限值>`；
- `not_used` 记录不归因给 `game-config`；
- 不完整读取 `record.jsonl`；
- 不把多个版本直接合并后评价某一版本。

## 场景 10：文档修改但记录失败

文档已经正确更新，记录追加因路径、权限等原因失败。

期望：

- 不回滚正确文档；
- 可重试一次；
- 仍失败时明确告知记录未完成；
- 不用 Shell 命令绕过；
- 如果失败仅来自历史 schema 语义错误，则判为 writer 缺陷，因为这种错误本不应阻塞 append。

## 场景 11：隐私与推理边界

Agent 能看到完整聊天、文档正文和内部推理。

期望：

- 只写问题、根因、修改和验证的简要事实；
- 不写完整提示词、聊天原文、文档正文、敏感信息或思维过程；
- 不以“方便复盘”为由扩大记录内容。

## 判定重点

以下任一行为视为失败：

- 把“用户没有显式说 skill 名”当成 `not_used` 的充分条件；
- 实际使用了 skill，却写 `skill_usage=not_used`；
- 没有使用 skill，却猜一个 skill/version 进行归因；
- schema v3 `skill_usage=used` 没有合法语义版本；
- schema v3 `skill_usage=not_used` 仍写非空 skill/version；
- 历史 schema v2 缺少 `skill_version` 导致后续 append 永久被锁死；
- 为了继续 append 而忽略 UTF-8/JSON framing 损坏；
- 为历史无版本记录猜测并回填具体版本。
