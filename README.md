# Game Development Skills

一组面向游戏研发需求、实现与日常维护协作的 Agent Skills。目标是让 Agent 根据任务真实复杂度选择最小可靠路径：复杂功能逐步收敛为可配置、可实现、可评审、可维护的工程结果；局部维护则直接调查、修改和验证，不为流程本身制造额外成本。

## 工作流

### 正式功能开发

```text
01 原始需求
  → 02 需求挖掘
  → 03 程序实现澄清
  → 04 配置规划
  → 05 框架实现
  → 06 完整实现
  → 客户端对接（按需）
  → 07 Review
  → 长期功能文档
```

简单需求保持单线；大需求可以从 `01` 开始按真实边界拆成 `Uxx` 工作单元，各单元独立推进和 Review。所有目标单元完成后，仅在存在集成风险时再执行整体 Review。

### 日常轻量维护

```text
调查真实事实
  → 最小正确修改
  → 按风险验证
  → 收尾
```

Bug 修复、小需求、局部重构和轻量 Review 默认不创建 `01–07` 阶段文档、Uxx、状态门禁或正式交叉 Review。只有任务实际越过产品规则、公共合同、数据模型、架构或组合风险边界时，才回到最早必要的正式 skill。

线上 Hotfix 单独处理：只有已经上线、存在真实玩家/存量数据，或用户明确要求按生产约束处理时，才默认深入考虑在线状态、历史数据、兼容、灰度、补偿和回滚。开发期不因“未来可能上线”提前背负这些成本。

这是一组可组合动作，不是不可逆的瀑布阶段。

## Skills

| Skill | 主要产物 | 作用 |
|---|---|---|
| `game-spec` | `01-原始需求.md` | 无损整理需求；按需拆分工作单元 |
| `game-discovery` | `02-需求挖掘.md` | 收敛真正需要需求负责人决定的问题 |
| `game-tech-clarify` | `03-程序实现澄清.md` | 收敛高影响技术决策 |
| `game-config` | `04-配置规划.md` | 确认配置真源、值域、关键值并完成配表验证 |
| `game-scaffold` | `05-框架实现方案.md` + 骨架 | 建立数据、同步、持久化和调用链框架 |
| `game-implement` | `06-完整实现方案.md` + 代码 | 补齐完整行为、边界、兼容、测试和运维闭环 |
| `game-client-handoff` | 客户端对接文档 | 维护服务端—客户端真实合同 |
| `game-review` | `07-*-交叉评审.md` | 独立 Review 工作单元，并按需做整体集成查漏 |
| `game-docs` | `docs/features/<feature>.md` | 提炼长期权威功能文档 |
| `game-bugfix` | 代码；维护记录按需 | 定位根因并完成最小正确修复与回归验证 |
| `game-small-change` | 代码；维护记录按需 | 沿现有机制实现规则明确的局部需求 |
| `game-refactor` | 代码；维护记录按需 | 在冻结外部行为的前提下改善局部结构 |
| `game-light-review` | 对话 Findings；评审记录按需 | 对维护型 diff 做证据驱动的局部 Review |
| `game-hotfix` | 修复；Hotfix 记录按需 | 在真实生产约束下止损、修复、发布与验证 |

## 设计与规范

- [`docs/skill-development/principles.md`](docs/skill-development/principles.md)：长期准则，只维护会改变设计、开发和维护取舍的简短条例。
- [`docs/skill-development/design.md`](docs/skill-development/design.md)：正式功能开发的仓库级设计，包含工作流模型、权威文档模型、阶段门禁、变更传播和审计记录机制。
- [`docs/skill-development/maintenance-workflow.md`](docs/skill-development/maintenance-workflow.md)：Bugfix、小需求、重构、轻量 Review 与 Hotfix 的轻量维护边界、环境规则、文档模型和升级条件。
- [`docs/skill-development/branch-workflow.md`](docs/skill-development/branch-workflow.md)：Uxx 拆分、依赖、命名、独立 Review 与整体 Review 的专项规范。
- 各 `skills/<skill-name>/SKILL.md`：单个 skill 的执行规则和场景细节。

README 只提供入口。长期取舍以准则文档为入口；正式功能跨 skill 规则以设计文档为准；轻量维护以 maintenance 专项规范为准；其他专项规则以对应规范和各 skill 自身规则为准。

## 安装

```bash
npx skills@latest add Sth32/skills
```

也可以只复制需要的 `skills/<skill-name>/` 目录到 Agent 的 skills 目录。

## 验证

运行静态验证：

```bash
python scripts/validate_skills.py
```

`evals/` 包含各 skill 的行为测试场景；分支工作流专项测试覆盖简单路径、需求层拆分、兄弟并行、多前驱、Step/Uxx 边界、客户端对接和 Review；轻量维护专项测试覆盖开发期/线上边界、升级条件和按需文档行为。
