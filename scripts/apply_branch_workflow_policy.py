#!/usr/bin/env python3
"""Apply the canonical requirement-first branch workflow across skills and docs."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
BRANCH_DOC = ROOT / "docs/skill-development/branch-workflow.md"
BRANCH_EVAL = ROOT / "evals/branch-workflow.md"
STAGE_POLICY = ROOT / "scripts/apply_stage_transition_policy.py"
SKILLS_DIR = ROOT / "skills"

VERSION_RE = re.compile(r'(\n\s*version:\s*")(\d+)\.(\d+)\.(\d+)("\s*\n)')
BRANCH_RULE_RE = re.compile(r"\*\*分支工作流硬限制：.*?\*\*", re.DOTALL)
ROOT_RULE_RE = re.compile(r"\*\*根文档硬限制：.*?\*\*", re.DOTALL)
DOCS_BRANCH_RULE_RE = re.compile(r"\*\*分支汇合输入规则：.*?\*\*", re.DOTALL)
README_WORKFLOW_RE = re.compile(r"## 工作流\n.*?(?=## 结构性变更影响传播\n)", re.DOTALL)

README_WORKFLOW_SECTION = """## 工作流

```text
原始材料
  ↓
01 需求层：简单需求保持单线；大需求可从这里开始拆 Uxx
  ├─ 共享 01（仅保留真正共享的需求基线）
  ├─ U01：01 → 02 → 03 → 04 → 05 → 06 → 客户端对接 → 07-U01 Review
  ├─ U02：01 → 02 → 03 → 04 → 05 → 06 → 客户端对接 → 07-U02 Review
  └─ U03：可依赖 U01/U02，也可继续拆分
          ↓
    各叶工作单元独立 Review 完成
          ↓
    按集成风险决定是否执行 07-交叉评审.md（整体查漏补缺）
          ↓
    项目长期功能文档
```

这些是可组合动作，不是不可逆的瀑布阶段。工作单元的价值是形成**独立需求边界、独立推进边界和独立 review 边界**；因此不再要求先把所有分支推进到同一阶段，也不要求在 review 前把分支重新合并。一个工作单元只检查自己的共享上游、直接依赖和当前阶段状态；无依赖兄弟分支不构成阻塞。

整体 Review 不是再次逐分支重做 Review。它只在所有目标工作单元已经各自 review 后，复用 `07-Uxx-*` 报告、客户端对接文档和当前代码/配置，重点检查跨分支需求覆盖、共享数据与时序、配置/RPC/事件冲突、合同缺口以及分支 Review 后的代码漂移。真正独立且不存在集成风险时可以不创建整体 `07-交叉评审.md`。

## 技能

| 技能 | 主要产物 | 负责解决的问题 |
|---|---|---|
| `game-spec` | `01-原始需求.md` / `01-Uxx-<主题>-原始需求.md` | 无损整理当前需求；需要多人独立推进时可直接在需求层创建工作单元 |
| `game-discovery` | `02-需求挖掘.md` / `02-Uxx-<主题>-需求挖掘.md` | 对当前工作单元只保留需要需求负责人决定的高价值未决问题 |
| `game-tech-clarify` | `03-程序实现澄清.md` / `03-Uxx-<主题>-程序实现澄清.md` | 收敛当前工作单元的高影响实现决策与真实未决技术问题 |
| `game-config` | `04-配置规划.md` / `04-Uxx-<主题>-配置规划.md` | 确认配置对象、真实配置源、关键值和修改范围，再配表并验证 |
| `game-scaffold` | `05-框架实现方案.md` / `05-Uxx-<主题>-框架实现方案.md` + 可运行骨架 | 确定数据权威、持久化、同步、客户端可见性和空 RPC 路由 |
| `game-implement` | `06-完整实现方案.md` / `06-Uxx-<主题>-完整实现方案.md` + 完整代码 | 沿已确认框架补齐行为、边界、失败、兼容、测试和运维闭环 |
| `game-client-handoff` | `<主题>-客户端对接文档.md` / `Uxx-<主题>-客户端对接文档.md` | 每个工作单元独立维护服务端到客户端合同，不等待兄弟分支 |
| `game-review` | `07-交叉评审.md` / `07-Uxx-<主题>-交叉评审.md` | 先独立 review 单个工作单元；全部完成后按需做整体集成查漏 |
| `game-docs` | `docs/features/<feature>.md` | 从当前实现、全部已完成分支 Review 及可选整体 Review 提炼长期权威文档 |

## 过程文档结构

未发生分支时保持原结构，不创建额外索引：

```text
docs/requirements/<feature>/
├── 01-原始需求.md
├── 02-需求挖掘.md
├── 03-程序实现澄清.md
├── 04-配置规划.md
├── 05-框架实现方案.md
├── 06-完整实现方案.md
├── <主题名>-客户端对接文档.md（按需）
├── 07-交叉评审.md
└── record.jsonl
```

第一次真正拆分后仍使用**同一目录**，禁止为分支增加一级子目录：

```text
docs/requirements/<feature>/
├── 00-工作流索引.md
├── 01-原始需求.md                         # 若存在共享需求，只保留共同基线
├── 01-U01-战斗-原始需求.md
├── 01-U02-奖励-原始需求.md
├── 02-U01-战斗-需求挖掘.md
├── 02-U02-奖励-需求挖掘.md
├── ...
├── 06-U01-战斗-完整实现方案.md
├── 06-U02-奖励-完整实现方案.md
├── U01-战斗-客户端对接文档.md（按需）
├── U02-奖励-客户端对接文档.md（按需）
├── 07-U01-战斗-交叉评审.md
├── 07-U02-奖励-交叉评审.md
├── 07-交叉评审.md                         # 可选：全部分支完成后的整体集成 Review
└── record.jsonl
```

**权威文档粒度是“工作单元 × 阶段”。** 每个工作单元在一个阶段最多维护一份权威过程文档；共享父文档只保存真实共享基线，不复制子单元事实。代码、配置源、Excel、测试、生成物、diff 和日志属于实际产物或证据，不计作过程文档。

`00-工作流索引.md` 只承担路由：工作单元 ID、范围、依赖、当前阶段、当前文档，以及整体 Review 的状态/指针。它不得复制需求规则、方案、配置值、验证结果、未决问题或阶段文档顶部状态。

`game-config` 的人工填表步骤、执行状态和验证结果仍写入当前工作单元的配置规划文档，不生成配置执行清单。策划配表说明仍是非权威交付物。

`game-client-handoff` 在未分支时继续使用 `<主题名>-客户端对接文档.md`；分支工作流中使用 `Uxx-<主题名>-客户端对接文档.md`。拆分前已经存在的共享合同可以作为共同基线，各工作单元只记录自己的新增或变化合同。

长期实现文档优先服从项目已有约定；没有约定时写入 `docs/features/<feature>.md`。

## 分支工作流

完整维护规范见 [`docs/skill-development/branch-workflow.md`](docs/skill-development/branch-workflow.md)。核心规则：

1. **最早从 01 拆分**：只要已经形成真实的独立需求边界，就可以创建 `Uxx`；不必等 `01` 整体完成。
2. **分支独立跑完整链路**：每个工作单元可以独立经过 `01`–`06`、客户端对接和 `07-Uxx` Review。
3. **不强制合并**：工作流拓扑不要求把多个 Uxx 合成一个父节点后才能 review 或交付。
4. **Review 不互相等待**：当前 Uxx 达到自己的 pre-review 门禁即可 review；无依赖兄弟分支的进度不构成阻塞。
5. **客户端对接同样独立**：当前 Uxx 的合同稳定后即可生成/更新自己的对接文档。
6. **整体 Review 是二次集成检查**：所有目标叶单元各自 review 后，再按共享代码、数据、协议、配置和发布耦合判断是否需要 `07-交叉评审.md`。
7. **简单路径零成本**：没有实际分支时不创建 `00` 或 `U01`，继续使用原文件名。
8. **首次拆分才建 `00`**：ID 使用稳定的 `U01`、`U02`……；串行、并行和多前驱依赖只写在索引中。
9. **禁止分支子目录**：所有工作单元文档与共享文档、`record.jsonl` 保持同目录。
10. **父节点拆分后停止直接推进**：父文档压缩为共同基线并标记 `已拆分`，后续由叶子后继推进。
11. **Step 与工作单元不同**：同一实现闭环内部的分批人工 review 用文档内 Step；只有真正独立的范围才拆 Uxx。
12. **变更只使受影响 Review 失效**：已 review 的 Uxx 若其需求、依赖合同或代码基线发生结构性变化，标记该 Uxx review 需要复核；不得机械让所有兄弟分支重新 review。

在所有 skill 中，“本阶段唯一文档”在分支模式下解释为：**当前工作单元在当前阶段的唯一权威文档**。共享父文档和 `00` 不与子工作单元竞争当前阶段权威。

"""

BRANCH_WORKFLOW_DOC = """# 分支工作流规范

本文定义 `docs/requirements/<feature>/` 下的工作单元模型。目标是让大需求在多人/多 Agent 协作时尽早形成独立需求边界，并允许每个分支独立推进、独立客户端对接和独立 Review；整体 Review 只承担最后的集成查漏，而不是再次把流程收回单线。

## 边界

- 简单需求保持单线：`01-原始需求.md` → `02` → … → `07-交叉评审.md`，不创建 `00` 或 Uxx。
- 工作单元最早可在 `01` 需求整理阶段创建，也可在后续 `02`–`06`、客户端对接或 Review 修复过程中继续拆分。
- 分支后每个叶工作单元都可以独立走到 `07-Uxx-<主题>-交叉评审.md`；无依赖兄弟分支不构成门禁。
- 分支不要求重新合并。所有目标叶单元各自 Review 完成后，才评估是否需要额外的整体 `07-交叉评审.md`。
- 所有过程文档始终位于同一个需求目录，禁止为 Uxx 增加子目录。

## 工作单元模型

工作单元使用稳定 ID：`U01`、`U02`、`U03`……。ID 只表达身份，不编码父子或先后；串行、并行和多前驱关系统一写在 `00-工作流索引.md`。

适合拆分的条件至少满足一项，并且拆分后边界能够说清：

- 有独立的产品需求/验收边界；
- 可以由不同 session 或 Agent 独立推进；
- 可以独立阻塞，而不应拖住兄弟范围；
- 可以独立完成客户端对接或 Review；
- 拆开能显著降低单次认知与人工 review 负担。

只属于同一实现闭环的连续步骤仍使用阶段文档内部 Step，不创建 Uxx。

## 文件命名

未分支沿用原名。分支后阶段文档统一使用：

```text
<阶段号>-<Uxx>-<主题>-<阶段名>.md
```

需求层同样适用：

```text
01-U01-战斗-原始需求.md
01-U02-奖励-原始需求.md
```

后续示例：

```text
03-U01-战斗-程序实现澄清.md
06-U01-战斗-完整实现方案.md
U01-战斗-客户端对接文档.md
07-U01-战斗-交叉评审.md
```

整体集成 Review 若需要，固定使用 `07-交叉评审.md`，不带 Uxx。

## 需求层拆分

`game-spec` 整理材料时，一旦已经能识别真实独立需求边界，或用户明确要求按多人协作拆分，可以直接创建工作单元：

1. 首次拆分创建 `00-工作流索引.md`。
2. 为每个范围分配稳定 Uxx，并创建对应 `01-Uxx-<主题>-原始需求.md`。
3. 如果已经存在 `01-原始需求.md`，只保留真正共享的规则；已被分配到子单元的规则移动到对应 Uxx，不复制。
4. 共享 `01` 若只是被拆分后的父节点，顶部状态写 `已拆分`；它是共享基线/路由终态，不代表任何子单元已完成。
5. 每个 Uxx 的 `01` 自己达到 `整理完成` 后，即可在满足实际依赖的前提下进入自己的 `02`，不等待其他 Uxx 的需求整理。

因此，分支工作流中的需求权威不是“唯一 01”，而是**当前工作单元适用的共享需求基线 + 自身/祖先 Uxx 需求文档**。

## `00-工作流索引.md`

第一次真正发生分支时创建：

```markdown
# <功能名>：工作流索引

> 首次分支来源：<阶段文档或 ROOT>
> 整体 Review：未评估 / 不需要 / `07-交叉评审.md`
> 最后更新：<YYYY-MM-DD>

| 单元 | 范围 | 依赖 | 当前阶段 | 当前文档 |
|---|---|---|---|---|
| U01 | <范围> | ROOT | 01 | `01-U01-...md` |
| U02 | <范围> | ROOT | 03 | `03-U02-...md` |
| U03 | <范围> | U01,U02 | 05 | `05-U03-...md` |
```

规则：

- `ROOT` 表示首次拆分前的共享基线；从已有 Uxx 继续拆分时，子单元依赖父单元。
- 索引只记录路由信息，不复制阶段正文或顶部状态。
- 阶段是否可推进必须读取实际阶段文档，不能从索引猜测。
- 当前 Uxx 进入 `07-Uxx` Review 后，索引的当前阶段/当前文档指向该 Review 文档。
- 所有目标叶单元 Review 完成后，必须做一次“整体 Review 是否必要”的判断；只有需要时才把整体 Review 指向 `07-交叉评审.md`。

## 创建或继续拆分

Agent 优先给出最短依赖模型，通常 2–5 个直接后继。用户明确要求拆分时直接执行；否则说明拆分理由、范围和依赖后再确认。

发生拆分时：

1. 首次拆分创建 `00`；已有则更新。
2. 新后继分配新的稳定 Uxx，不复用旧 ID。
3. 当前父文档压缩为仍然有效的共同基线并标记 `已拆分`。
4. 分支专属事实移动到子文档，共享事实只引用，不复制。
5. 父工作单元停止直接进入下一阶段，由叶后继继续。

## 分支阶段门禁

存在 `00` 时，任一阶段开始前只解析当前 Uxx 的真实依赖：

- 检查当前工作单元适用的共享需求基线、自身/祖先需求文档、直接前驱和当前阶段要求的上游；
- 无依赖兄弟工作单元可以位于任意阶段；
- 多前驱单元必须等待自己声明的前驱达到所需稳定状态；
- 上游结构性变化只让实际受影响的下游文档与 Review 失效，不机械扩散到无关兄弟分支；
- 每个“工作单元 × 阶段”最多一份权威文档。

## 分支 Review

每个叶工作单元独立进入 Review：

1. 定位当前 Uxx 的需求基线、实际 `02`–`06` 链路、代码/配置 diff 和客户端对接文档。
2. 当前 Uxx 自身达到 pre-review 终态即可开始 `07-Uxx-<主题>-交叉评审.md`。
3. 不等待无依赖兄弟 Uxx，也不要求先把代码或文档“合并成一个工作单元”。
4. Review 发现上游问题时，只回写/修复受影响的当前 Uxx 或真实依赖；修复后原位更新当前 `07-Uxx`。
5. Review 发现当前范围应再拆分时，可暂停该 Uxx Review，回到最早合适阶段创建子 Uxx；新叶单元各自 Review 后，原父 Review 只保留仍有价值的共享结论。

## 客户端对接

客户端对接与 Review 一样按工作单元独立推进：当前 Uxx 的服务端合同稳定到足以对接时即可创建/更新 `Uxx-<主题>-客户端对接文档.md`。共享合同可保留一份共同基线；兄弟 Uxx 只记录自己的新增/变化合同。

## 整体 Review

当所有本次目标叶单元均已通过各自 Review 后，Agent 评估是否需要整体 `07-交叉评审.md`。

需要整体 Review 的典型条件：共享代码/数据权威、同一状态机、配置表、RPC/事件命名空间、客户端合同、迁移/发布顺序或其他组合运行风险。真正独立且不存在这些耦合时可以跳过，并在 `00` 写 `整体 Review：不需要`。

整体 Review 的输入必须优先使用：

- 全部分支 `07-Uxx-*` 的已确认结论；
- 全部分支客户端对接文档；
- 共享需求基线与各 Uxx 需求文档；
- 当前组合代码、配置、生成物和测试证据。

整体 Review 只做查漏补缺：需求覆盖缺口、跨分支冲突、共享事实重复/矛盾、接口与客户端合同不一致、依赖/时序问题、分支 Review 后代码漂移。不得机械重做每个 Uxx 已经有证据覆盖的内部 Review。

整体 Review 发现问题时把问题路由回 owning Uxx 或新建独立 Uxx；只让受影响 Review 失效。修复完成后原位更新对应分支 Review，并继续整体 Review 的受影响检查。
"""

BRANCH_EVAL = """# 分支工作流行为评估

用于回归“需求层即可拆分、工作单元独立 Review、整体 Review 只做集成查漏”的工作流协议。所有过程文档保持在同一个 `docs/requirements/<feature>/` 目录。

## 场景 1：简单需求零额外成本

范围紧凑且无需独立推进。

期望：继续使用 `01-原始需求.md` 到 `07-交叉评审.md`；不创建 `00` 或 Uxx。

## 场景 2：在 01 阶段直接拆分

原始材料已经明显分成“战斗”和“奖励”，可以由两位开发独立推进。

期望：首次拆分创建 `00`；创建 `01-U01-战斗-原始需求.md` 与 `01-U02-奖励-原始需求.md`；共享 `01` 只保留真正共同规则，不复制子单元内容；任一 Uxx 的 01 完成后可以独立进入 02。

失败：要求先把整个 `01-原始需求.md` 整理完成后才能拆；禁止 `01-Uxx-*`。

## 场景 3：兄弟分支不互相阻塞

U01 已进入 06，U02 仍在 03，二者无依赖。

期望：U01 可以继续实现、客户端对接并在自身满足门禁后进入 `07-U01-*`；U02 不构成阻塞。

## 场景 4：依赖仍由 DAG 表达

U03 依赖 U01,U02。

期望：U03 等待自己声明的前驱达到所需稳定状态；不通过 `U01.1` 等 ID 编码拓扑；调整依赖不重命名文件。

## 场景 5：实现 Step 不冒充工作单元

同一 U01 需要三次人工 review，但不能独立交付。

期望：继续维护一份 `06-U01-*` 并用 Step 1/2/3，不机械创建 U02/U03。

## 场景 6：客户端对接跟随工作单元

U01 与 U02 有不同客户端合同。

期望：分别维护 `U01-*-客户端对接文档.md` 与 `U02-*-客户端对接文档.md`；任一分支合同稳定后即可推进，不等待兄弟分支；共享合同只引用共同基线。

## 场景 7：单分支可以先 Review

U01 的 06 已完成且合同稳定，U02 仍在实现中，二者无依赖。

期望：创建/更新 `07-U01-*-交叉评审.md` 并完成 U01 Review；不创建整体 `07-交叉评审.md` 冒充全部完成；U02 后续独立 Review。

失败：因为 U02 未完成而拒绝 review U01；强制所有叶单元汇合后才能进入 game-review。

## 场景 8：Review 发现需要继续拆分

U01 Review 发现其中一块应形成独立生命周期。

期望：暂停受影响的 U01 Review，回到最早合适阶段创建新 Uxx；无关已通过分支保持有效；新叶分支各自 Review 后再更新受影响结论。

## 场景 9：整体 Review 只做集成查漏

U01、U02 都已通过各自 Review，二者共享数据和客户端协议。

期望：评估并创建 `07-交叉评审.md`；先读取两个分支 Review 与客户端对接文档；重点检查共享数据、协议、时序、需求覆盖和 Review 后漂移，不重复逐项重做 U01/U02 内部 Review。

## 场景 10：真正独立时可跳过整体 Review

多个 Uxx 没有共享代码、数据、协议、配置或发布耦合。

期望：允许在 `00` 标记 `整体 Review：不需要`；后续长期文档读取全部已完成分支 Review 和当前代码，不因缺少整体 `07-交叉评审.md` 而阻塞。
"""

SPEC_TEMPLATE = """<!--
阶段完成门禁：聊天中的“整理完成”不构成阶段完成。当前叶需求文档只有在完成检查、把顶部状态写为 `整理完成`、同步最后更新并重新读取确认后，才能进入自己的 `game-discovery`。若当前文档被继续拆分，顶部状态写 `已拆分`，由叶子后继继续；`已拆分` 不是需求完成。
-->

# <功能名>：原始需求

> 状态：整理完成 / 存在待确认原文 / 已拆分  
> 工作单元：<未分支或共享文档省略；分支文档写 Uxx>  
> 来源：<材料名称、日期或链接>  
> 最后更新：<YYYY-MM-DD>  
> 范围：<用一句话说明当前文档覆盖范围；来源未明确时省略>

## 需求规则

### <按实际问题、流程或主题命名>

1. <主体 + 条件 + 行为 + 结果；相关数值、状态、限制、失败结果和例外直接写在相邻位置>
2. <同一问题的下一条独立规则>

<!--
同一问题的条件、行为、结果、数值、限制与例外必须相邻；同一个需求事实只能出现一次。
分支模式下，共享规则只留在共享/父需求文档，Uxx 文档只写自己的需求事实并引用共享基线，不复制正文。

除“需求规则”外，仅当来源确实包含内容时按需追加：

## 明确排除
- <来源明确要求不处理或不在当前范围的内容>

## 冲突与原文待确认
- `C-001` <冲突差异与来源；引用规则编号，不完整复制规则正文>
- `U-001` <无法唯一理解或无法识别的原始片段>

没有内容时不要创建章节，也不要写“无”。沟通得到新结论后原位替换旧描述，文档只保留当前有效需求。
-->
"""

REVIEW_TEMPLATE = """<!--
启动门禁：先判断当前是未分支 Review、某个 Uxx 的分支 Review，还是全部分支完成后的整体 Review。分支 Review 只检查当前 Uxx 的共享需求基线、真实依赖、实际 02–06 链路、代码/配置和当前客户端合同；无依赖兄弟分支不构成阻塞。整体 Review 只在目标叶单元已分别 Review 后启动，并优先复用它们的 Review 报告与客户端对接文档做集成查漏。
阶段完成门禁：最终结论必须先写回本文档顶部 `状态` 并同步最后更新时间，再重新读取确认写入成功，之后才能宣布通过、有条件通过或不通过。
-->

# <功能名或工作单元>：交叉评审

> 状态：评审中 / 通过 / 有条件通过 / 不通过
> Review 类型：未分支 / 分支 Uxx / 整体集成
> 工作流：<无 00 / `00-工作流索引.md`>
> 基线：<base>..<head>
> 文档版本：
> 最后更新：

## 1. Review 范围

- 工作单元：<未分支/整体时按实际填写>
- 代码：
- 配置与导表：
- 需求与方案：<当前 Uxx 的共享基线 + 自身链路 / 整体时为全部分支 Review 与需求>
- 客户端对接：
- 排除项：
- 验证限制：

## 2. Reviewer 分工

| Reviewer | 独立视角 | 使用方法 | 状态 |
|---|---|---|---|

## 3. 已确认发现

| ID | 工作单元 | 级别 | 根因与触发场景 | 证据位置 | 影响 | 处理结论 | 复审 |
|---|---|---|---|---|---|---|---|

## 4. 被证伪或合并的候选

| 候选 | 工作单元 | 原判断 | 证伪/合并证据 | 结论 |
|---|---|---|---|---|

## 5. 文档与测试问题

| ID | 工作单元 | 类型 | 问题 | 影响 | 处理 |
|---|---|---|---|---|---|

## 6. 验证证据

- 构建/启动：
- 关键测试：
- 配置/迁移：
- 故障与回滚：

## 7. 最终结论

- 状态：
- 未解决 S0/S1：
- 接受的条件或风险：
- 建议下一步：

<!--
分支 Review 的发现只路由到当前 Uxx 或其真实依赖；整体 Review 可以标记 owning Uxx/shared。
若 Review 发现需要新的独立工作单元，回到最早合适阶段扩展 DAG，只让受影响 Review 失效，不机械重跑无关兄弟分支。
-->
"""


def bump_patch_version(text: str) -> str:
    match = VERSION_RE.search(text)
    if not match:
        raise ValueError("missing semantic metadata version")
    major, minor, patch = map(int, match.group(2, 3, 4))
    replacement = f'{match.group(1)}{major}.{minor}.{patch + 1}{match.group(5)}'
    return text[: match.start()] + replacement + text[match.end() :]


def sub_once(text: str, pattern: re.Pattern[str], replacement: str, *, label: str) -> str:
    new_text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one match, got {count}")
    return new_text


def replace_required(text: str, old: str, new: str, *, label: str) -> str:
    if old not in text:
        raise ValueError(f"{label}: missing expected anchor: {old[:80]!r}")
    return text.replace(old, new, 1)


def patch_skill_file(path: Path, patcher) -> str:
    old = path.read_text(encoding="utf-8")
    new = patcher(old, path)
    if new == old:
        return old
    return bump_patch_version(new)


def requirement_baseline_wording(text: str) -> str:
    replacements = (
        ("唯一的 `01-原始需求.md`", "当前工作单元适用的需求基线"),
        ("唯一 `01-原始需求.md`", "当前工作单元适用的需求基线"),
        ("唯一的 `01`", "当前工作单元适用的需求基线"),
        ("唯一 `01`", "当前工作单元适用的需求基线"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def stage_branch_rule(stage_no: str, filename: str) -> str:
    return (
        "**分支工作流硬限制：工作单元最早可在 `01` 需求整理阶段创建，并可独立推进到客户端对接和 `07-Uxx` Review；"
        "不存在“所有分支先汇合才能 review”的门禁。当前阶段若发现真实独立范围，仍可继续拆分稳定工作单元 `U01`、`U02`……；"
        "所有文件保持在同一个 `docs/requirements/<feature>/` 目录，不增加分支子目录。没有真实分支时继续使用原文件名。"
        "第一次拆分创建 `00-工作流索引.md`，只记录 ID、范围、依赖、当前阶段、当前文档和整体 Review 指针；拓扑只由依赖表达。"
        f"分支文档命名为 `{stage_no}-<Uxx>-<主题>-{filename}.md`。当前 Uxx 只检查自己的共享需求基线、自身/祖先需求文档和真实依赖；"
        "无依赖兄弟工作单元不构成阻塞。**"
    )


def patch_spec(text: str, path: Path) -> str:
    text = replace_required(
        text,
        "把分散、口语化、重复或结构混乱的需求材料，整理为简洁的 `01-原始需求.md`。",
        "把分散、口语化、重复或结构混乱的需求材料整理为简洁的需求基线；简单需求维护 `01-原始需求.md`，需要多人独立推进时可直接在本阶段拆成 `01-Uxx-<主题>-原始需求.md`。",
        label=str(path),
    )
    new_root_rule = (
        "**需求分支硬限制：`01` 是最早允许形成工作单元的阶段。只要材料已经呈现真实独立需求边界，或用户明确要求按多人/多 Agent 协作拆分，"
        "即可在本阶段创建 `00-工作流索引.md` 与 `01-Uxx-<主题>-原始需求.md`；不得强迫先完成一份覆盖全部范围的 `01-原始需求.md`。"
        "若拆分前已有 `01-原始需求.md`，只保留真正共享的规则，分支专属事实移动到对应 Uxx，不复制；父需求文档可标记 `已拆分`。"
        "每个叶 Uxx 的 `01` 达到 `整理完成` 后即可在满足自身真实依赖时进入 `02`，不等待无依赖兄弟分支。没有真实独立边界时仍保持单一 `01-原始需求.md`，不为形式统一制造 Uxx。**"
    )
    text = sub_once(text, ROOT_RULE_RE, new_root_rule, label=str(path))
    product_re = re.compile(r"## 产物\n.*?(?=## 输入范围\n)", re.DOTALL)
    product = """## 产物

未分支默认写入：

```text
docs/requirements/<feature>/01-原始需求.md
```

需要在需求层拆分时，同目录创建：

```text
docs/requirements/<feature>/00-工作流索引.md
docs/requirements/<feature>/01-U01-<主题>-原始需求.md
docs/requirements/<feature>/01-U02-<主题>-原始需求.md
```

使用 [原始需求模板](references/原始需求模板.md)。`01-原始需求.md` 在分支模式下只保存真正共享的需求基线；每个 `01-Uxx` 只保存当前工作单元专属需求。一个需求事实只能属于一个权威位置，不得为了让分支“自包含”复制共享正文。

"""
    text = sub_once(text, product_re, product, label=str(path))
    text = text.replace(
        "- 因为预期后续会并行开发就在 `01` 阶段提前拆文件。",
        "- 仅因为需求很大或预期并行就机械拆分；只有真实独立需求/review 边界才创建 Uxx。",
    )
    insert_anchor = "### 5. 围绕实际规则组织内容\n"
    if insert_anchor not in text:
        raise ValueError(f"{path}: missing workflow step 5 anchor")
    branch_step = """### 5. 判断是否需要在需求层拆工作单元

整理出原子事实后，检查是否已经存在多个可以独立确认、独立推进、独立阻塞或独立 review 的需求范围。用户已明确要求按工作单元协作时直接按最短依赖模型拆分；否则只有拆分能降低协作耦合时才提出拆分。

发生拆分时先更新 `00`，再把分支专属事实移动到对应 `01-Uxx`；共享规则留在共享父需求文档。每个 Uxx 独立继续本阶段整理，不要求兄弟工作单元同步完成。

"""
    text = text.replace(insert_anchor, branch_step + "### 6. 围绕实际规则组织内容\n", 1)
    text = text.replace("### 6. 仅按需创建特殊章节", "### 7. 仅按需创建特殊章节", 1)
    text = text.replace("### 7. 沟通后更新当前真相", "### 8. 沟通后更新当前真相", 1)
    text = text.replace("### 8. 做覆盖、重复与结构检查", "### 9. 做覆盖、重复与结构检查", 1)
    text = text.replace(
        "- 不在 `01` 阶段创建工作单元或工作流索引。",
        "- 无真实独立边界时不创建工作单元；需要拆分时可在 `01` 阶段直接创建 `00` 与 `01-Uxx`。",
    )
    text = text.replace(
        "| 内容已变化但只在聊天中说明 | 同一轮更新 `01-原始需求.md`，并明确告知用户路径 |",
        "| 内容已变化但只在聊天中说明 | 同一轮更新当前权威 `01` / `01-Uxx`，并明确告知用户路径 |",
    )
    text = text.replace(
        "| 大需求在 01 就拆成多个文件 | 01 保持唯一共同根；完成后再由后续阶段决定是否创建 Uxx |",
        "| 已有独立需求边界却坚持整个 01 单线完成 | 在 01 创建 Uxx，让各工作单元独立整理和推进 |",
    )
    return text


def patch_stage(text: str, path: Path, stage_no: str, stage_name: str) -> str:
    text = sub_once(text, BRANCH_RULE_RE, stage_branch_rule(stage_no, stage_name), label=str(path))
    text = requirement_baseline_wording(text)
    if path.parent.name == "game-discovery":
        text = text.replace(
            "**文档职责：`01` 保存整个需求的当前有效产品规则；",
            "**文档职责：未分支时 `01-原始需求.md` 保存全部当前产品规则；分支时由共享需求基线与当前/祖先 `01-Uxx` 共同构成当前工作单元的产品规则；",
            1,
        )
        text = text.replace(
            "必须先有且只允许有一份 `01-原始需求.md`。",
            "必须先确认当前工作单元适用的共享需求基线与自身/祖先 `01-Uxx` 已达到当前阶段所需的可移交状态。",
            1,
        )
    if path.parent.name == "game-implement":
        text = text.replace(
            "一个工作单元完成不代表所有工作单元完成，也不代表可以开始完整 `game-review`。",
            "一个工作单元完成后可以在满足自身门禁时进入 `07-Uxx` Review；这不代表其他工作单元完成，也不代表已经需要或可以开始整体 `07-交叉评审.md`。",
            1,
        )
    return text


def patch_client(text: str, path: Path) -> str:
    rule = (
        "**分支工作流硬限制：工作单元最早可在 `01` 创建，并可独立推进客户端对接与 `07-Uxx` Review。"
        "当前 Uxx 的服务端属性/RPC/事件合同稳定到足以对接时即可创建或更新自己的 `Uxx-<主题>-客户端对接文档.md`，不等待无依赖兄弟分支。"
        "若调查证明范围需要继续拆分，也可更新 `00-工作流索引.md` 创建新 Uxx。所有文件保持同目录；ID 只表达身份，依赖只写在 `00`。"
        "分支对接文档只记录当前 Uxx 的合同，拆分前共享合同通过引用继承。**"
    )
    text = sub_once(text, BRANCH_RULE_RE, rule, label=str(path))
    return requirement_baseline_wording(text)


def patch_review(text: str, path: Path) -> str:
    text = text.replace(
        "description: Use when a game feature has requirements, implementation decisions, configuration changes, code, and tests ready for evidence-based cross-review by multiple independent agents before merge, release, or final documentation.",
        "description: Use when one game-feature work unit or an already branch-reviewed feature needs evidence-based cross-review by multiple independent agents, either for an independent Uxx review or an optional final integration-gap review.",
        1,
    )
    intro_re = re.compile(r"## 目标\n.*?(?=\*\*文档更新时序硬限制)", re.DOTALL)
    intro = """## 目标

对**当前 review 范围**的需求链路、配置、方案、代码和测试做独立交叉验证。未分支时维护 `07-交叉评审.md`；分支时每个工作单元独立维护 `07-Uxx-<主题>-交叉评审.md`；所有目标工作单元分别 Review 后，如存在真实集成风险，再额外维护整体 `07-交叉评审.md` 做查漏补缺。

**核心原则：让不同 reviewer 从不同失效模型出发独立找问题，再互相证伪；不以意见数量代替代码证据。**

**Review 粒度硬限制：一个 review 文档只对应一个明确范围。** 分支 Review 只覆盖当前 Uxx 及其真实依赖；整体 Review 只覆盖跨分支集成风险。不同 Uxx 可以分别拥有自己的 `07-Uxx-*`，但同一个 Uxx 不得按 reviewer、轮次、修复验证再拆第二份报告；所有 reviewer 原始输出仍只是临时输入。

**独立 Review 硬限制：存在 `00-工作流索引.md` 时，不得要求所有叶工作单元先汇合。** 当前 Uxx 的共享需求基线、自身/祖先需求文档、实际 `02`–`06` 链路、代码/配置和当前客户端合同达到 pre-review 条件后即可开始 `07-Uxx-*`；无依赖兄弟分支不构成阻塞。依赖前驱只需达到当前 Uxx 所需的稳定状态；若前驱后续结构性变化影响已 Review 的 Uxx，只让受影响 Review 失效并复核。

**整体 Review 硬限制：整体 `07-交叉评审.md` 不是分支 Review 的替代品，也不是强制汇合门禁。** 只有所有本次目标叶单元已经分别 Review 后，才根据共享代码、数据、配置、协议、客户端合同或发布时序等耦合判断是否需要整体 Review。需要时必须优先复用各 `07-Uxx-*` 与客户端对接文档，只检查需求覆盖缺口、跨分支冲突、共享事实不一致、接口/合同缺口和 Review 后代码漂移；真正独立时可以不创建整体 Review。

"""
    text = sub_once(text, intro_re, intro, label=str(path))
    old_actual = "本阶段的“实际前置”由 Review 汇合硬限制定义：存在 `00` 时不是某一条单线 `01`–`06`，而是共享根 + 所有叶工作单元各自真实 pre-review 链路。"
    new_actual = "本阶段的实际前置由当前 Review 类型决定：分支 Review 只检查当前 Uxx 的需求基线、真实依赖和 pre-review 链路；整体 Review 则要求本次目标叶工作单元已经分别 Review 完成。"
    text = replace_required(text, old_actual, new_actual, label=str(path))
    text = text.replace(
        "`00-工作流索引.md` 的 Review 汇合指针由本 skill 更新时，也必须按同一记录规则追加 `record.jsonl`。",
        "本 skill 更新 `00-工作流索引.md` 的当前阶段/当前文档或整体 Review 指针时，也必须按同一记录规则追加 `record.jsonl`。",
        1,
    )
    pre_re = re.compile(r"## 前置条件与产物\n.*?(?=## Review 范围固定\n)", re.DOTALL)
    pre = """## 前置条件与产物

### 未分支

读取 `01`–`06`、客户端对接文档、代码/配置 diff、测试与运行证据。正常进入要求单线 `01=整理完成`、`02=已收敛`、`03=已收敛`、`04=已完成`、`05=骨架已完成`、`06=已完成`，以及实际存在的客户端合同达到可移交状态。

产物：

```text
docs/requirements/<feature>/07-交叉评审.md
```

### 分支工作单元 Review

先读取 `00` 定位当前 Uxx，再读取：

1. 当前 Uxx 适用的共享需求基线与自身/祖先 `01-Uxx`；
2. 当前 Uxx 实际需要的 `02`–`06` 链路和直接依赖；
3. 当前 Uxx 的代码、配置、生成物、测试和客户端对接文档；
4. 依赖前驱对当前 Uxx 有约束力的稳定合同/证据。

当前 Uxx 自身达到 pre-review 终态即可开始，不等待无依赖兄弟分支。产物：

```text
docs/requirements/<feature>/07-<Uxx>-<主题>-交叉评审.md
```

### 整体集成 Review

只有本次目标叶工作单元已经分别 Review 完成后才评估是否需要。若不存在共享代码、数据、配置、协议、客户端合同或发布耦合，可在 `00` 标记 `整体 Review：不需要`。需要时创建/继续：

```text
docs/requirements/<feature>/07-交叉评审.md
```

整体 Review 的主要输入是全部相关 `07-Uxx-*`、客户端对接文档与当前组合代码/配置证据，而不是重新从零逐分支 Review。

使用 [交叉评审模板](references/交叉评审模板.md)。

"""
    text = sub_once(text, pre_re, pre, label=str(path))
    scope_re = re.compile(r"## Review 范围固定\n.*?(?=## 多 Agent 结构\n)", re.DOTALL)
    scope = """## Review 范围固定

开始前记录仓库/分支/基线/目标提交和当前 Review 类型。

- **未分支 Review**：覆盖单线需求、方案、配置、代码、测试与客户端合同。
- **Uxx Review**：只覆盖当前工作单元 + 共享需求基线 + 它真实依赖的合同；不把无关兄弟分支塞入 review 包。
- **整体 Review**：覆盖全部已完成分支 Review、全部相关客户端对接文档、共享基线与跨工作单元集成面；默认信任分支 Review 中仍然有效的已证实结论，只对组合风险和证据漂移重新检查。

review 期间范围或代码基线变化时立即更新当前 review 文档；结构性变化导致既有结论失效时，只标记实际受影响的 Uxx/整体检查重新验证。

"""
    text = sub_once(text, scope_re, scope, label=str(path))
    text = text.replace(
        "1. **需求一致性 reviewer**：检查所有工作单元合起来是否完整满足唯一 `01`，是否遗漏、篡改、重复实现或跨单元冲突。",
        "1. **需求一致性 reviewer**：分支 Review 检查当前 Uxx 是否满足其共享/专属需求基线；整体 Review 检查全部分支合起来是否存在覆盖缺口、篡改、重复实现或跨单元冲突。",
        1,
    )
    text = text.replace(
        "- 独立通过的工作单元合并后是否出现集成冲突；",
        "- 多个已通过工作单元组合运行时是否出现集成冲突；",
        1,
    )
    text = text.replace("### 4. 协调者写入唯一 `07`", "### 4. 协调者写入当前 Review 文档", 1)
    text = text.replace(
        "只把有明确位置或路径、具体影响、不是纯偏好、未被现有证据反证、修复价值足够的发现写入 `07`。每条发现标记所属 `Uxx` 或 `shared`，同一根因只保留一条。",
        "只把有明确位置或路径、具体影响、不是纯偏好、未被现有证据反证、修复价值足够的发现写入当前 Review 文档。分支 Review 默认归属当前 Uxx；整体 Review 标记 owning `Uxx` 或 `shared`。同一根因只保留一条。",
        1,
    )
    text = text.replace(
        "2. 明确指出需要修订的具体 `02-Uxx`/`03-Uxx`/`04-Uxx`/`05-Uxx`/`06-Uxx`，或共享 `01`/共享上游，并说明拟修改内容；",
        "2. 明确指出需要修订的具体 `01-Uxx`/`02-Uxx`/`03-Uxx`/`04-Uxx`/`05-Uxx`/`06-Uxx`，或共享 `01`/共享上游，并说明拟修改内容；",
        1,
    )
    split_re = re.compile(r"### 6\. review 中需要新增工作单元\n.*?(?=## 输出结论\n)", re.DOTALL)
    split = """### 6. Review 中需要新增或重拆工作单元

如果 Review 证明某块范围应拥有独立生命周期：

1. 暂停**受影响**的当前 Review，并记录根因与范围；
2. 回到最早合适的 `01`–`06` 阶段更新 `00`，创建新的稳定 Uxx；
3. 只让依赖该范围的既有 Review 失效，无关兄弟分支保持已通过状态；
4. 新叶工作单元分别完成自己的 `07-Uxx` Review；
5. 若当前是整体 Review，回到原 `07-交叉评审.md` 只复核受影响集成项。

工作流不要求把新旧 Uxx 再次合并成一个 review 单元。

"""
    text = sub_once(text, split_re, split, label=str(path))
    text = text.replace(
        "最终状态写入唯一 `07` 顶部并立即告知用户。若存在 `00`，其 Review 汇合继续指向同一 `07`，不创建“review 完成后的新分支状态”。",
        "最终状态写入当前 Review 文档顶部并立即告知用户。分支 Review 完成后让 `00` 的当前阶段/当前文档指向该 `07-Uxx`；整体 Review 若执行，则由 `00` 的整体 Review 指针指向 `07-交叉评审.md`。",
        1,
    )
    common_re = re.compile(r"## 常见错误\n.*\Z", re.DOTALL)
    common = """## 常见错误

| 错误 | 正确处理 |
|---|---|
| U01 已完成但 U02 还在实现，因此拒绝 review U01 | 若二者无依赖，直接 review U01 |
| 所有 Uxx 都必须先汇合到一份 07 | 每个 Uxx 维护自己的 `07-Uxx-*`；整体 07 只按集成风险创建 |
| 整体 Review 再逐项重做每个分支 Review | 复用分支报告和客户端对接，只查跨分支缺口与证据漂移 |
| 分支 Review 忽略共享需求或直接依赖 | Review 包包含当前 Uxx 的共享基线与真实依赖合同 |
| 一个依赖变化让所有分支 Review 全失效 | 只标记实际依赖该变化的 Review 复核 |
| 每个 reviewer 各写一份报告 | 同一 Review 范围内原始输出仅临时，统一写入当前 Review 文档 |
| 修复后另建复审报告 | 原位更新同一发现 |
| Review 发现新独立范围却继续塞回当前 Uxx | 回到最早合适阶段创建新 Uxx，再独立 Review |
| 以多个 Agent 同意作为证据 | 回到代码、配置、测试和触发路径 |
| 发现上游错误后直接改写 | 先列明具体文档与拟修改内容并获得确认 |
"""
    text = sub_once(text, common_re, common, label=str(path))
    banned = (
        "强制汇合",
        "禁止创建 `07-Uxx",
        "所有叶工作单元先闭环，再统一进入",
        "最终只在一个 review 结论上收敛",
        "唯一 `07`",
    )
    for phrase in banned:
        if phrase in text:
            raise ValueError(f"{path}: stale review workflow phrase remains: {phrase}")
    return text


def patch_docs(text: str, path: Path) -> str:
    new_rule = (
        "**分支 Review 输入规则：过程工作流若存在 `00-工作流索引.md`，必须用它定位全部实际工作单元，并确认本次纳入长期文档的叶工作单元都已完成各自 `07-Uxx-*` Review。"
        "整体 `07-交叉评审.md` 仅在确有集成风险时存在；存在则必须达到可交付终态并作为额外证据，不存在不得单独成为阻塞。"
        "`00` 只用于定位材料，不得把 Uxx、DAG、阶段状态或任务进度写入长期权威文档。**"
    )
    text = sub_once(text, DOCS_BRANCH_RULE_RE, new_rule, label=str(path))
    text = replace_required(
        text,
        "本阶段的实际前置是已完成的整体 `game-review`：未分支时读取单线 `01`–`07`；已分支时读取 `00`、所有仍有解释价值的分支材料与唯一 `07`。不要求长期文档复刻分支结构。",
        "本阶段的实际前置是：未分支时单线 `07-交叉评审.md` 已完成；已分支时本次范围所有叶工作单元的 `07-Uxx-*` 已完成。整体 `07-交叉评审.md` 若存在也必须完成，但它不是分支模式的强制前置。长期文档不复刻分支结构。",
        label=str(path),
    )
    text = text.replace(
        "- 唯一 `07-交叉评审.md` 及其最终结论；",
        "- 未分支时的 `07-交叉评审.md`，或分支模式下全部相关 `07-Uxx-*` 的最终结论；整体 `07-交叉评审.md` 若存在也一并读取；",
        1,
    )
    text = text.replace(
        "3. 唯一 `07` 的最新 review 结论；",
        "3. 当前范围全部有效的分支 review 结论，以及存在时的整体 review 最新结论；",
        1,
    )
    text = text.replace("5. 唯一 `01` 和早期讨论。", "5. 当前工作单元适用的共享/专属需求基线和早期讨论。", 1)
    gate_re = re.compile(r"### 1\. 验证 review 已汇合\n.*?(?=### 2\. 确定模块边界\n)", re.DOTALL)
    gate = """### 1. 验证 Review 覆盖

先查找 `00-工作流索引.md`：

- 不存在：确认单线 `07-交叉评审.md` 已达到可交付终态；
- 存在：确认本次范围所有叶工作单元都有已完成的 `07-Uxx-*` Review；若 `00` 指向整体 `07-交叉评审.md`，也确认其达到可交付终态；若 `00` 明确 `整体 Review：不需要`，不得因为没有整体 07 而阻塞。

不满足时停止正常长期文档生成，明确指出具体未完成工作单元或 Review；不得在长期文档阶段替代缺失 Review。

"""
    text = sub_once(text, gate_re, gate, label=str(path))
    text = text.replace(
        "- 已确认全部分支在唯一 `07` 汇合并达到可交付终态；",
        "- 已确认本次范围全部叶工作单元分别 Review 完成，且需要时整体 Review 也已完成；",
        1,
    )
    text = requirement_baseline_wording(text)
    stale = ("未汇合叶工作单元", "Review 汇合指向唯一", "全部分支在唯一 `07` 汇合")
    for phrase in stale:
        if phrase in text:
            raise ValueError(f"{path}: stale docs workflow phrase remains: {phrase}")
    return text


def patch_stage_policy(text: str, path: Path) -> str:
    text = replace_required(
        text,
        "| 01 原始需求 | `01-原始需求.md` | `整理完成` |",
        "| 01 原始需求 | 未分支 `01-原始需求.md`；分支 `01-Uxx-<主题>-原始需求.md` | 叶文档 `整理完成`；父文档可为 `已拆分` |",
        label=str(path),
    )
    text = replace_required(
        text,
        "| 07 交叉评审 | `07-交叉评审.md` | `通过`；`有条件通过` 仅按已明确接受的条件继续 |",
        "| 07 交叉评审 | 未分支/整体 `07-交叉评审.md`；分支 `07-Uxx-<主题>-交叉评审.md` | `通过`；`有条件通过` 仅按已明确接受的条件继续 |",
        label=str(path),
    )
    return text


def write_if_changed(path: Path, new_text: str, *, check: bool) -> bool:
    old = path.read_text(encoding="utf-8")
    if old == new_text:
        return False
    if not check:
        path.write_text(new_text, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed: list[Path] = []
    try:
        readme_old = README.read_text(encoding="utf-8")
        readme_new = sub_once(readme_old, README_WORKFLOW_RE, README_WORKFLOW_SECTION, label=str(README))
        if write_if_changed(README, readme_new, check=args.check):
            changed.append(README)

        if write_if_changed(BRANCH_DOC, BRANCH_WORKFLOW_DOC, check=args.check):
            changed.append(BRANCH_DOC)
        if write_if_changed(BRANCH_EVAL, BRANCH_EVAL, check=args.check):
            changed.append(BRANCH_EVAL)

        spec = SKILLS_DIR / "game-spec/SKILL.md"
        if write_if_changed(spec, patch_skill_file(spec, patch_spec), check=args.check):
            changed.append(spec)

        spec_template = SKILLS_DIR / "game-spec/references/原始需求模板.md"
        if write_if_changed(spec_template, SPEC_TEMPLATE, check=args.check):
            changed.append(spec_template)

        stage_specs = {
            "game-discovery": ("02", "需求挖掘"),
            "game-tech-clarify": ("03", "程序实现澄清"),
            "game-config": ("04", "配置规划"),
            "game-scaffold": ("05", "框架实现方案"),
            "game-implement": ("06", "完整实现方案"),
        }
        for skill_name, (stage_no, stage_name) in stage_specs.items():
            path = SKILLS_DIR / skill_name / "SKILL.md"
            patcher = lambda text, p, n=stage_no, s=stage_name: patch_stage(text, p, n, s)
            if write_if_changed(path, patch_skill_file(path, patcher), check=args.check):
                changed.append(path)

        client = SKILLS_DIR / "game-client-handoff/SKILL.md"
        if write_if_changed(client, patch_skill_file(client, patch_client), check=args.check):
            changed.append(client)

        review = SKILLS_DIR / "game-review/SKILL.md"
        if write_if_changed(review, patch_skill_file(review, patch_review), check=args.check):
            changed.append(review)
        review_template = SKILLS_DIR / "game-review/references/交叉评审模板.md"
        if write_if_changed(review_template, REVIEW_TEMPLATE, check=args.check):
            changed.append(review_template)

        docs = SKILLS_DIR / "game-docs/SKILL.md"
        if write_if_changed(docs, patch_skill_file(docs, patch_docs), check=args.check):
            changed.append(docs)

        stage_policy_old = STAGE_POLICY.read_text(encoding="utf-8")
        stage_policy_new = patch_stage_policy(stage_policy_old, STAGE_POLICY)
        if write_if_changed(STAGE_POLICY, stage_policy_new, check=args.check):
            changed.append(STAGE_POLICY)

        # Guard the core policy against future accidental regression.
        for path in [
            SKILLS_DIR / "game-discovery/SKILL.md",
            SKILLS_DIR / "game-tech-clarify/SKILL.md",
            SKILLS_DIR / "game-config/SKILL.md",
            SKILLS_DIR / "game-scaffold/SKILL.md",
            SKILLS_DIR / "game-implement/SKILL.md",
            SKILLS_DIR / "game-client-handoff/SKILL.md",
        ]:
            candidate = (path.read_text(encoding="utf-8") if not args.check else patch_skill_file(path, (
                patch_client if path.parent.name == "game-client-handoff" else
                (lambda text, p, spec=stage_specs[path.parent.name]: patch_stage(text, p, spec[0], spec[1]))
            )))
            for stale in ("`01-原始需求.md` 永远只有一份", "`01` 完成后到 `game-review` 启动前"):
                if stale in candidate:
                    raise ValueError(f"{path}: stale branch policy remains: {stale}")

    except (OSError, ValueError) as exc:
        print(f"branch workflow policy application failed: {exc}", file=sys.stderr)
        return 2

    if changed:
        prefix = "NEEDS UPDATE" if args.check else "UPDATED"
        for path in changed:
            print(f"{prefix} {path.relative_to(ROOT)}")
        return 1 if args.check else 0

    print("Branch workflow policy is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
