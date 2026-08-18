# Game Development Skills

一组面向游戏研发需求与实现协作的 Agent Skills。目标是把口述需求逐步收敛为可配置、可实现、可评审、可维护的工程结果，同时保持策划、服务端与客户端的职责边界。

## 工作流

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

## 设计与规范

- [`docs/skill-development/design.md`](docs/skill-development/design.md)：仓库级设计，包含工作流模型、权威文档模型、阶段门禁、变更传播、`record.jsonl` 和统一设计原则。
- [`docs/skill-development/branch-workflow.md`](docs/skill-development/branch-workflow.md)：Uxx 拆分、依赖、命名、独立 Review 与整体 Review 的专项规范。
- 各 `skills/<skill-name>/SKILL.md`：单个 skill 的执行规则和阶段细节。

README 只提供入口。跨 skill 的设计规则以设计文档为准；专项规则以对应规范和各 skill 自身规则为准。

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

`evals/` 包含各 skill 的行为测试场景；分支工作流专项测试覆盖简单路径、需求层拆分、兄弟并行、多前驱、Step/Uxx 边界、客户端对接和 Review 等场景。
