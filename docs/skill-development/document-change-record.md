# 文档变更记录机制

## 目标

`record.jsonl` 用于捕获 Agent 在生成和维护文档时暴露出的真实问题，为 skill、模板、eval 和工具改进提供证据。

它不承担当前需求、方案或实现状态的表达。权威内容仍只存在于对应阶段文档中。

记录系统必须区分两个概念：

- **是否实际使用了 skill**；
- **用户是否显式写出了 skill 名称**。

后者不能作为归因依据。Agent 根据描述自动命中并实际加载/执行某个 skill，也属于使用了该 skill；反过来，如果一次修改没有实际使用任何 skill，就不能为了凑字段把它归因到某个已安装 skill。

## 为什么使用 JSONL

每条记录是一行独立 JSON。这个格式的核心价值是**行级隔离**：

- 新记录只追加，不重写历史；
- 历史增长不要求把全文加载进 Agent 上下文；
- 一条旧记录的字段语义错误不应让后面的独立记录永久无法写入；
- UTF-8 或 JSON framing 损坏则会破坏文件可读性，必须阻止继续追加。

因此，写入路径只负责保证“文件仍是可逐行解析的 UTF-8 JSONL”；严格 schema 审计由 `check` 单独负责。

## 文件位置

在目标文档所在目录维护：

```text
<document-directory>/record.jsonl
```

同一目录内多个文档共用该文件，通过 `documents` 字段区分。一次修改涉及多个目录时，每个目录分别追加，只记录该目录内实际变化的文档。

## 何时追加

每次逻辑上的文档变更完成后追加一条：

- 创建文档；
- 修改文档；
- 删除文档；
- 重命名或迁移文档。

只讨论、没有落盘变化时不记录。向 `record.jsonl` 自身追加不触发新的记录。

## Schema v3：skill 归因

当前新记录使用 `schema_version=3`，新增 `skill_usage`。

### 实际使用了 skill

```json
{
  "schema_version": 3,
  "skill_usage": "used",
  "skill": "game-implement",
  "skill_version": "0.1.9"
}
```

要求：

- `skill_usage=used`；
- `skill` 为实际执行的 skill；
- `skill_version` 必须是该 skill 当前 `SKILL.md -> metadata.version`；
- 版本由当前 skill 自带写入器自动读取，Agent 不传、不猜、不沿用历史值；
- 用户没有显式说“使用某 skill”不影响判断，只要 Agent 实际加载/执行了该 skill，就按 `used` 记录。

### 实际没有使用任何 skill

```json
{
  "schema_version": 3,
  "skill_usage": "not_used",
  "skill": null,
  "skill_version": null
}
```

此时使用：

```bash
python <writer> append ... --no-skill
```

要求：

- 不得选一个“最像”的 skill 代替；
- 不得把当前仓库最新 skill 版本填进去；
- 不得写 `unknown` 冒充某个具体 skill 的版本；
- 查询和统计时，该类记录归入 `skill=none`、`skill_version=not_applicable`。

`--skill` 与 `--no-skill` 互斥，必须二选一。

## 历史版本兼容

历史记录保持原字节内容，不静默迁移：

- schema v1 没有 `skill_version`：查询/统计视为 `unknown`；
- 合法 schema v2：保留其语义版本；
- 历史 schema v2 若缺少或带非法 `skill_version`：这是**历史 schema 语义错误**，`check` 必须报告，但不能阻塞后续独立 append；查询/统计按 `skill_version=unknown` 处理；
- 不根据时间、提交、相邻记录或“当时大概用了哪个 skill”回填历史版本。

这正是 JSONL 行级隔离的意义：坏的历史归因证据要被暴露，但不能把整个审计链锁死。

## append 与 check 的职责分离

### `append` 的前置检查

append 只阻止会继续破坏文件结构的问题：

1. 文件不是普通文件；
2. 任一已有非空行不是 UTF-8；
3. 任一已有非空行不是完整 JSON；
4. 任一已有非空行不是 JSON object。

只要现有文件仍是可逐行解析的 UTF-8 JSONL，历史行的字段缺失、旧 schema 不完整等**语义问题不得阻塞新行追加**。

### `check` 的严格检查

`check` 对所有非空行做完整 schema 检查。它负责发现：

- schema v2 缺少合法 `skill_version`；
- schema v3 缺少 `skill_usage`；
- `skill_usage=used` 但 skill/version 不合法；
- `skill_usage=not_used` 却仍写入 skill/version；
- 未支持的 schema 版本。

所以：

- append 成功 ≠ 历史记录全部健康；
- check 失败 ≠ 后续 append 必须停止；
- 只有存储层 UTF-8/JSONL 损坏才同时阻止 append。

## skill 版本取值硬限制

当 `skill_usage=used` 时，每个 `skills/<skill-name>/` 必须自带：

```text
scripts/document_record.py
```

调用：

```bash
python <skill-root>/scripts/document_record.py append \
  --skill <skill-name> ...
```

写入器根据自身路径定位 `<skill-root>/SKILL.md`，并要求：

1. `SKILL.md` 存在且为 UTF-8；
2. frontmatter 中存在 `name`；
3. `metadata.version` 是 `x.y.z`；
4. `--skill` 与该 `SKILL.md` 的 `name` 完全一致。

任一条件不满足都拒绝本次 `used` 记录，防止错误使用其他 skill 的写入器或伪造版本。

## 必填信息

| 字段 | 含义 |
|---|---|
| `schema_version` | 新记录当前为 `3` |
| `timestamp` | 带时区 ISO 8601 时间 |
| `skill_usage` | `used` 或 `not_used` |
| `skill` | 使用 skill 时为实际 skill；未使用时为 `null` |
| `skill_version` | 使用 skill 时为实际语义版本；未使用时为 `null` |
| `runtime` | Agent 运行环境，未知写 `unknown` |
| `model` | 实际模型名，未知写 `unknown` |
| `reasoning_effort` | 实际思考等级，未知写 `unknown` |
| `action` | `create` / `update` / `delete` / `rename` |
| `documents` | 本次实际变更的相对路径 |
| `trigger` | 初次生成、用户反馈、自检、review、测试失败、代码变化、上游变化或其他 |
| `problem` | 为什么需要本次变更 |
| `root_cause` | 根因；不确定写 `unknown` |
| `change_summary` | 实际改了什么，不复制正文 |
| `validation` | 验证状态和最小证据 |
| `outcome` | `success` / `partial` / `failed` |
| `improvement` | skill、模板、eval、工具或项目上下文的防复发建议 |
| `commit` | 可选提交标识 |

## UTF-8 与写入限制

写入器：

- 使用 UTF-8（无 BOM）编码；
- 使用二进制 `O_APPEND` 单次追加完整 JSON 行；
- append 前只校验现有文件的 UTF-8/JSON object 结构；
- 不把历史全文返回给 Agent；
- 不在普通 append 中修复、重排、迁移或删除历史行。

禁止直接使用：

- Shell `>`、`>>`、`echo`；
- PowerShell `Add-Content`、`Set-Content`、`Out-File`；
- 依赖系统默认编码的通用文本写入 API；
- 写入器失败后用其他命令绕过。

## 查询边界

Agent 不得直接 `cat` 或完整打开 `record.jsonl`。

允许：

1. `check`：严格验证文件和 schema，只返回错误位置；
2. `query`：按 skill、skill version、skill usage、文档、触发原因、结果等过滤，只返回最近有限条；
3. `stats`：流式扫描，只返回聚合统计。

示例：

```bash
python <writer> query \
  --record <path>/record.jsonl \
  --skill game-implement \
  --skill-version 0.1.9 \
  --tail 20

python <writer> query \
  --record <path>/record.jsonl \
  --skill none \
  --skill-usage not_used \
  --tail 20

python <writer> stats \
  --record <path>/record.jsonl
```

查询历史非法 schema 行时，工具会警告并按 best-effort 数据保留；版本缺失归入 `unknown`，而不是丢弃整条历史证据。

## 从记录到 skill 改进

评估 skill 时只使用 `skill_usage=used` 的记录，并按明确 `skill_version` 分组。

`not_used` 记录的作用是区分“通用 Agent 行为问题”和“skill 行为问题”，避免把没有使用 skill 的失败错误归因给某个版本。

分析顺序：

1. 用 `stats` 查看 skill usage、skill version 和 release 分布；
2. 对具体版本用受限 `query` 抽取少量案例；
3. 把 `not_used` 与具体 skill 版本分开分析；
4. 判断根因属于 skill、模板、eval、工具还是项目上下文；
5. 修改最靠近根因的位置，并补回归 eval；
6. 后续同版本/新版本不再出现该根因，才认为改进有效。

## 失败与并发

文档已经正确更新但记录追加失败时，不回滚正确文档。

- 如果是权限、路径或暂时性写入失败，可重试一次；
- 如果是 UTF-8/JSON framing 损坏，明确报告并停止追加；
- 如果只是历史 schema 语义错误，不得把它当作 append 阻塞条件；
- 多个 Agent 同时维护同一目录时，每个 Agent 各追加一条完整记录，不合并或重写他人的历史。
