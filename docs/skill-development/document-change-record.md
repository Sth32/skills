# 文档变更记录机制

## 目标

`record.jsonl` 用于捕获 Agent 在生成和维护文档时暴露出的真实问题，为 skill、模板、eval 和工具改进提供证据。

它不承担当前需求、方案或实现状态的表达。权威内容仍只存在于对应阶段文档中。

由于 skill 会滚动升级，**每条新记录必须绑定产生它的具体 skill 版本**。否则不同版本的记录长期混合后，会把旧版本缺陷错误归因到新版本，或掩盖一次升级是否真正改善了问题。

## 为什么使用 JSONL

- 每次变更只追加一行，不需要把历史内容加载进 Agent 上下文；
- 每条记录是独立 JSON，便于过滤、统计和自动评审；
- 历史增长不会迫使 Agent 总结旧记录或复制正文；
- 相比 Markdown 流水账，更适合后续提取重复失效模式。

## 文件位置

在目标文档所在目录维护：

```text
<document-directory>/record.jsonl
```

同一目录内多个文档共用该文件，通过 `documents` 字段区分。一次修改涉及多个目录时，每个目录必须分别追加，只记录该目录内实际变化的文档。`record.jsonl` 是审计元数据，不属于阶段过程文档，因此不违反“一个阶段一份权威文档”。

## 何时追加

每次逻辑上的文档变更完成后追加一条：

- 创建文档；
- 修改文档；
- 删除文档；
- 重命名或迁移文档。

同一目录内，一次操作因同一原因同时修改多个文档时，可以写一条记录并列出全部路径。若多个修改对应不同问题或根因，应分别记录；若跨越多个目录，则每个目录各写一条。

仅讨论但没有落盘变化时不记录。向 `record.jsonl` 自身追加不触发新的记录。当前暂不收紧触发范围，先保留足够样本，再依据后续真实反馈判断哪些记录属于稳定噪声。

## Schema 与版本兼容

当前新记录使用 `schema_version=2`。

- schema v2 新增必填字段 `skill_version`；
- `skill_version` 必须等于本次实际运行 skill 的 `SKILL.md -> metadata.version`；
- 版本由当前 skill 自带的写入器自动读取，Agent 不传、不猜、不手填；
- schema v1 历史记录没有版本信息，必须保持原样，在查询和统计时统一视为 `skill_version=unknown`；
- 不允许根据时间、Git 提交、文件修改时间或“当时大概是哪版”去回填旧记录，因为这些推断会制造虚假的评估精度。

版本字段表达的是**产生这条记录时实际使用的 skill 版本**，不是当前仓库最新版本，也不是后续修复后的版本。

## 必填信息

| 字段 | 含义 |
|---|---|
| `schema_version` | 记录结构版本；新记录当前为 `2` |
| `timestamp` | 带时区的 ISO 8601 时间 |
| `skill` | 本次使用的 skill |
| `skill_version` | 实际运行 skill 的 `metadata.version`，由写入器自动读取 |
| `runtime` | Agent 运行环境或 Harness，如 `codex-cli`；未知写 `unknown` |
| `model` | 实际模型名；未知写 `unknown`，不得推测 |
| `reasoning_effort` | 实际思考等级；未知写 `unknown`，不得推测 |
| `action` | `create`、`update`、`delete` 或 `rename` |
| `documents` | 本次实际变更的相对路径数组 |
| `trigger` | 初次生成、用户反馈、自检、review、测试失败、代码变化、上游变化或其他 |
| `problem` | 为什么需要本次变更；尽量同时写清预期与实际差异，初次生成可写目标 |
| `root_cause` | 导致问题的根因；不确定时写 `unknown`，初次生成写 `not_applicable` |
| `change_summary` | 实际改了什么，不复制正文 |
| `validation` | 修复后的验证状态与最小证据，不用于替代问题证据 |
| `outcome` | `success`、`partial` 或 `failed` |
| `improvement` | 应改进的 skill、模板、eval、工具或项目上下文；`prevention` 必须描述防复发机制，不写普通项目待办 |
| `commit` | 可选提交标识 |

记录应描述可观察事实，不要求 Agent 给自己打主观质量分。

## skill 版本取值硬限制

每个 `skills/<skill-name>/` 目录都必须自带同一份：

```text
scripts/document_record.py
```

即使只安装或复制单个 skill，也必须调用该 skill 自带的脚本：

```bash
python <skill-root>/scripts/document_record.py append ...
```

写入器根据自身路径定位：

```text
<skill-root>/SKILL.md
```

然后读取 `name` 和 `metadata.version`。追加前必须满足：

1. `SKILL.md` 存在且为 UTF-8；
2. frontmatter 中存在 `name`；
3. `metadata.version` 是 `x.y.z` 形式的语义版本；
4. 命令的 `--skill` 与 `SKILL.md` 中的 `name` 完全一致。

任一条件不满足都拒绝追加。**新记录不得把 `skill_version` 写成 `unknown`。** 这能避免错误调用其他 skill 的写入器、复制后版本信息丢失或 Agent 手工沿用旧版本造成评估污染。

## UTF-8 写入硬限制

该脚本同时：

- 使用 UTF-8（无 BOM）编码 JSON；
- 使用二进制 `O_APPEND` 完成一次追加；
- 追加前在进程内部流式校验现有文件为 UTF-8 JSONL；
- 对 schema v2 记录额外校验 `skill_version`；
- 校验内容不返回给 Agent，不造成上下文污染；
- 发现已有文件编码、JSON 结构或 schema v2 版本字段异常时拒绝继续追加，避免继续污染记录。

禁止直接使用以下方式写入 `record.jsonl`：

- Shell `>`、`>>`、`echo`；
- PowerShell `Add-Content`、`Set-Content`、`Out-File`；
- 依赖系统默认编码的通用文本写入 API；
- 写入器失败后改用其他命令绕过。

找不到脚本、无法解析当前 skill 版本、已有记录不是有效 UTF-8 JSONL 或追加失败时，必须明确告知用户并停止记录写入。旧文件修复属于一次显式迁移，可以在用户确认后处理，但不得在普通 append 中静默重写历史。

## 写入边界

必须：

- 在文档变更后立即调用当前 skill 自带写入器；
- 一次追加一条完整 JSON；
- 让写入器自动写入实际 `skill_version`；
- 对未知模型、思考等级或运行环境明确写 `unknown`；
- 记录失败时明确告知用户，不得静默声称闭环完成。

禁止：

- 让 Agent 手工传入、覆盖或猜测 `skill_version`；
- 为了记录而把 `record.jsonl` 全文注入 Agent 上下文；
- 直接重写、排序、压缩或总结历史记录后再追加；
- 写入完整提示词、文档正文、聊天原文、用户敏感信息或思维过程；
- 为了显得完整而虚构根因、验证、模型或版本信息；
- 把记录文件当作需求、方案或实现事实来源。

## 查询边界

Agent 不得直接 `cat`、完整打开或把整个 `record.jsonl` 注入上下文。

允许三种方式：

1. `check`：只验证文件是否为 UTF-8 JSONL；schema v2 同时验证版本字段，不返回历史内容；
2. `query`：按 skill、`skill_version`、文档、触发原因、结果或改进目标过滤，只返回最近有限条目；
3. `stats`：程序流式扫描，只返回聚合计数，并按 `skill_version` / `skill@version` 分组。

示例：

```bash
python <skill-root>/scripts/document_record.py query \
  --record <path>/record.jsonl --skill game-config --skill-version 0.3.8 --outcome failed --tail 20

python <skill-root>/scripts/document_record.py stats \
  --record <path>/record.jsonl --skill game-config
```

`query` 默认最多返回 20 条，硬上限 200 条。需要进一步分析时继续缩小过滤条件，而不是扩大读取范围。

## 滚动版本评估规则

评估 skill 改进效果时，版本是分析边界，不是普通标签：

1. 先用 `stats --skill <name>` 查看 `skill_version` 和 `skill_release` 分布；
2. 比较升级前后时，分别按明确版本过滤，不把多个版本直接合并后下结论；
3. `skill_version=unknown` 的 schema v1 历史记录只能作为“旧版总体背景”，不能归因到任一具体版本；
4. 如果一个版本样本量过少，应明确标记证据不足，而不是与其他版本合并制造样本量；
5. 观察某类 root cause 是否在新版本中消失、下降或转化为新问题，再判断改进是否有效；
6. 版本发布后仍持续出现旧根因，才进一步判断是规则未生效、安装未更新、模型差异还是 eval 缺口。

这使 record 可以回答两个不同问题：**“这个 skill 长期最常见的问题是什么”**，以及更重要的 **“某个具体版本是否比上一版更好”**。

## 从记录到 skill 改进

记录只有进入以下闭环才有价值：

1. 使用 `stats` 找出重复出现的 trigger、root cause、improvement target 和版本分布；
2. 使用带 `--skill-version` 的受限 `query` 抽取少量代表性案例；
3. 判断根因属于 skill 指令、模板、eval、工具还是项目上下文；
4. 修改最靠近根因的位置，避免只增加提醒性补丁；
5. 为可复现失效模式增加 eval；
6. 运行静态验证与 eval，确认新规则不会制造新的冗余或越界；
7. 在后续**具体版本**的记录中不再出现该根因，才视为改进有效。

单次偶发问题不一定需要增加规则。重复出现、影响高或难以被人工发现的问题，应优先转化为硬限制、静态检查或回归 eval。

## 失败与并发

文档写入成功但记录追加失败时，文档仍是当前事实；Agent 必须报告记录失败并重试一次，不能回滚正确文档，也不能隐藏缺口。若失败原因是编码、结构或版本校验不通过，不得重试直接追加，也不得降级使用 Shell，应转为显式修复。

`scripts/document_record.py` 使用单次追加写，避免普通并发下的覆盖。多个 Agent 同时维护同一目录时，仍应让每个 Agent 各写一条完整记录，不合并或重写其他 Agent 的记录。
