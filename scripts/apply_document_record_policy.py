#!/usr/bin/env python3
"""Apply canonical stage-document policies across this repository."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
README = ROOT / "README.md"
VALIDATOR = ROOT / "scripts" / "validate_skills.py"
CANONICAL_WRITER = ROOT / "scripts" / "document_record.py"
BUNDLED_WRITER_RELATIVE = Path("scripts/document_record.py")

DOCUMENT_TIMING_RULE = (
    "**文档更新时序硬限制：任何新事实、确认、执行结果或验证结果只要改变本阶段内容，"
    "必须在同一轮立即原位更新本阶段唯一文档，并明确告知用户已更新的文件路径；"
    "不得等到阶段结束、批次结束或用户再次提醒。发现结论会改变更早阶段文档时，"
    "必须主动说明受影响文档和拟修改内容，先获得用户确认，再更新上游文档；"
    "未确认前不得静默改写。**"
)

DOCUMENT_IMPACT_RULE = (
    "**结构性变更影响传播硬限制：当范围、阶段状态、接口/RPC/事件合同、数据权威、工作单元依赖或配置真源发生变化时，"
    "必须在同一轮执行影响扫描，不得只修当前局部段落。当前阶段文档内至少核对顶部元信息、相关正文规则/矩阵、验证结论、"
    "阻塞与下一动作；同时定位已有且实际依赖该事实的上下游阶段文档、客户端合同与 `00-工作流索引.md` 中的旧引用。"
    "当前阶段和本 skill 允许直接维护的下游内容立即原位更新；若受影响的是需要用户确认才能改写的上游文档，必须明确列出"
    "受影响文件、旧事实与拟修改内容并等待确认，不得静默遗漏，也不得把未传播完成的结构性变化描述为已闭环。**"
)

DOCUMENT_CONSISTENCY_RULE = (
    "**阶段完成一致性硬限制：在宣布本阶段完成、确认或移交前，必须对本阶段权威文档做一次一致性收敛。"
    "同一事项不得同时保留互斥的当前状态、数值、操作要求或验证结论；发现冲突时，必须依据最新用户确认、"
    "实际源、代码或配置、生成物以及验证证据判定唯一当前事实并原位改写，删除被覆盖、错误、过时或仅用于过程追踪的内容。"
    "若证据不足无法判定，则该事项保持未完成或阻塞，只保留唯一待确认点，不得以“已完成”结束阶段。**"
)

DOCUMENT_RECORD_RULE = (
    "**文档变更记录硬限制：每次逻辑上的文档变更完成后，在目标文档所在目录的 `record.jsonl` 追加一条 JSON 记录；"
    "同一原因、同一轮、同一目录内的原子变更只记录一次，用 `documents` 列出全部实际变化文件，只有根因、结果或验证边界不同才拆记录。"
    "`record.jsonl` 自身追加不触发再次记录。新记录使用 schema v4：必须记录 skill usage/skill/version、运行环境、模型、思考等级、action、"
    "documents、trigger、reason、change summary、validation、outcome；正常进度使用 `feedback.signal=none`，不得为了填字段虚构问题、根因或预防建议。"
    "只有出现值得后续学习的偏差时才写 feedback：疑似可泛化但证据未足用 `candidate`；已经能定位根因且可形成防复发规则用 `actionable`，"
    "并填写稳定可复用的 snake_case `pattern`、severity、category、root_cause 与 prevention。用户改变需求使用 `trigger=user_change`；"
    "用户指出 Agent/文档错误使用 `trigger=user_correction`，两者不得混为同一质量信号。跨需求重复、skill 流程遗漏、模板诱导遗漏或 review 发现的"
    "通用缺陷不得默认归为 `project_context`；应归到最靠近根因的 `skill`/`template`/`eval`/`tooling`/`agent_execution`，"
    "只有确实依赖单一项目缺失事实时才用 `project_context`。只要当前 Agent 实际加载/执行了本 skill，就必须调用本 skill 自带的"
    " `scripts/document_record.py append --skill <当前skill>`，skill version 由写入器从当前 `SKILL.md` 自动读取；实际没有使用任何 skill 才可 `--no-skill`。"
    "历史 v1/v2/v3 保持原字节；append 只因非 UTF-8、非法 JSON 或非 object 等存储层损坏而拒绝，历史 schema 语义问题只由 `check` 报告。"
    "禁止使用 shell/PowerShell 文本重定向或通用文本 API 绕过写入器。需要评审记录时使用受限 `query`、`stats` 或 `report`，不得把全文注入上下文；"
    "评价 skill 必须按 `skill_usage=used` 和明确 `skill_version` 分组，并结合 report 的 metadata coverage 判断模型/运行环境比较是否有足够样本。"
    "禁止写入完整提示词、正文、用户敏感信息或思维过程。**"
)

TECH_CONTRACT_RULE = (
    "**跨边界通信合同硬限制：只要当前工作单元跨实体、线程、进程或 Server/Client 边界，03 必须把关键事实按最小合同矩阵澄清："
    "事实/数据、权威拥有者、内部路由、客户端是否可见、传输载体、标识类型、生命周期。内部 Host/View、路由镜像或服务端方法不得因为名称相似"
    "就被推断成客户端可见合同；无法从 Schema/Defs/生成物/注册点或实际调用链证明的能力必须保持未确认。**"
)

SCAFFOLD_RUNTIME_CHAIN_RULE = (
    "**框架真实链路硬限制：框架完成不能只证明类型、字段、RPC 或空方法“已经定义”。对本阶段实际新增的跨层路径，必须沿"
    "定义/Schema → 生成物或注册 → 暴露/路由 → 权威实体到达 → 技术失败返回形成最小可达证据；配置或属性若声明会被后续运行时使用，"
    "必须至少定位真实消费入口，不能把“字段存在/导表成功”当成“运行链路已接入”。Server 内部可调用方法不等于 Client RPC 可达。**"
)

IMPLEMENT_RUNTIME_CHAIN_RULE = (
    "**真实消费链验证硬限制：对本工作单元实际涉及的接口、配置、权限、异步或持久化路径，不能以“定义存在/代码已写/测试局部通过”作为闭环。"
    "应按风险追踪真实链路：定义/配置真源 → 生成/注册 → 暴露或寻址 → 权限检查对象 → 最终执行对象 → 运行时消费/副作用 → 状态生命周期 →"
    " 异步与失败路径 → 持久化/重启恢复 → 发布/回滚；只检查当前功能实际经过的节点。重点证明授权对象与执行对象一致、旧异步回包不会覆盖新状态、"
    " target missing/closing/expire 等终态能封口、时间事实使用一致时钟，以及 rollback 是可执行路径而非文档口号。缺少关键证据时保持未完成或显式风险。**"
)

CLIENT_REACHABILITY_RULE = (
    "**客户端合同可达性硬限制：客户端对接文档只能描述能够从实际客户端可见 Schema/Defs/生成协议、Observer/View/Event 或 RPC 注册与调用链证明的合同。"
    "服务端存在同名方法、内部 Host/View、线程路由或测试桩都不能单独证明客户端可见或可调用。每个新增/变化 RPC、事件和属性至少核对"
    "“定义 → 生成/注册 → 客户端可见载体 → 服务端接收/权威处理”的真实路径；任一环缺证据就写成缺口，不得包装成已交付能力。**"
)

TIMING_RULE_RE = re.compile(r"\*\*文档更新时序硬限制：.*?\*\*", re.DOTALL)
IMPACT_RULE_RE = re.compile(r"\*\*结构性变更影响传播硬限制：.*?\*\*", re.DOTALL)
CONSISTENCY_RULE_RE = re.compile(r"\*\*阶段完成一致性硬限制：.*?\*\*", re.DOTALL)
RECORD_RULE_RE = re.compile(r"\*\*文档变更记录硬限制：.*?\*\*", re.DOTALL)
VERSION_RE = re.compile(r'(\n\s*version:\s*")(\d+)\.(\d+)\.(\d+)("\s*\n)')

TARGETED_RULES = {
    "game-tech-clarify": (
        TECH_CONTRACT_RULE,
        "**核心原则：先查明事实，只讨论高影响决策；问题越往后越少。**",
    ),
    "game-scaffold": (
        SCAFFOLD_RUNTIME_CHAIN_RULE,
        "**框架不是功能的简化实现。框架阶段只确定数据放在哪里、谁是权威、如何持久化和同步、消息经过哪些实体；不实现产品规则。**",
    ),
    "game-implement": (
        IMPLEMENT_RUNTIME_CHAIN_RULE,
        "**核心原则：沿既定框架完成行为闭环；复杂实现按可 review 的纵向闭环分步推进；真正可以独立推进的范围拆工作单元；发现框架根因问题时修订框架，不在细节层堆补丁。**",
    ),
    "game-client-handoff": (
        CLIENT_REACHABILITY_RULE,
        "**核心边界：描述 Server 提供的合同，不设计客户端内部架构。**",
    ),
}

TARGETED_MARKERS = {
    "game-tech-clarify": "**跨边界通信合同硬限制：",
    "game-scaffold": "**框架真实链路硬限制：",
    "game-implement": "**真实消费链验证硬限制：",
    "game-client-handoff": "**客户端合同可达性硬限制：",
}

README_VALIDATOR_PARAGRAPH = (
    "验证器会要求每个 `SKILL.md` 包含统一的文档更新、结构性变更影响传播、阶段完成一致性与记录硬限制；"
    "对技术澄清、框架、完整实现和客户端对接技能额外检查跨层合同/真实消费链规则；"
    "对 `02`–`06` 和客户端对接技能检查分支工作流协议，对 `game-review` 检查 07 汇合协议，"
    "并检查每个 skill 自带的 UTF-8 写入器与仓库规范版本完全一致。"
)


def bump_patch_version(text: str) -> str:
    match = VERSION_RE.search(text)
    if not match:
        raise ValueError("missing semantic metadata version")
    major, minor, patch = map(int, match.group(2, 3, 4))
    replacement = f'{match.group(1)}{major}.{minor}.{patch + 1}{match.group(5)}'
    return text[: match.start()] + replacement + text[match.end() :]


def replace_or_insert_rule(
    text: str,
    rule: str,
    rule_re: re.Pattern[str],
    *,
    after_re: re.Pattern[str],
    path: Path,
    label: str,
) -> tuple[str, bool]:
    if rule in text:
        return text, False
    if rule_re.search(text):
        return rule_re.sub(rule, text, count=1), True
    anchor = after_re.search(text)
    if not anchor:
        raise ValueError(f"{path}: missing {label} insertion anchor")
    return text[: anchor.end()] + "\n\n" + rule + text[anchor.end() :], True


def insert_after_exact(text: str, anchor: str, block: str, path: Path) -> tuple[str, bool]:
    if block in text:
        return text, False
    if anchor not in text:
        raise ValueError(f"{path}: targeted rule anchor not found")
    return text.replace(anchor, anchor + "\n\n" + block, 1), True


def patch_skill(text: str, path: Path) -> str:
    changed = False

    text, did_change = replace_or_insert_rule(
        text,
        DOCUMENT_IMPACT_RULE,
        IMPACT_RULE_RE,
        after_re=TIMING_RULE_RE,
        path=path,
        label="impact rule",
    )
    changed |= did_change

    text, did_change = replace_or_insert_rule(
        text,
        DOCUMENT_CONSISTENCY_RULE,
        CONSISTENCY_RULE_RE,
        after_re=IMPACT_RULE_RE,
        path=path,
        label="consistency rule",
    )
    changed |= did_change

    text, did_change = replace_or_insert_rule(
        text,
        DOCUMENT_RECORD_RULE,
        RECORD_RULE_RE,
        after_re=CONSISTENCY_RULE_RE,
        path=path,
        label="record rule",
    )
    changed |= did_change

    target = TARGETED_RULES.get(path.parent.name)
    if target:
        rule, anchor = target
        text, did_change = insert_after_exact(text, anchor, rule, path)
        changed |= did_change

    return bump_patch_version(text) if changed else text


def insert_rule_after_heading(text: str, heading: str, rule: str, label: str) -> str:
    anchor = heading + "\n"
    if anchor not in text:
        raise ValueError(f"README: {label} section anchor not found")
    return text.replace(anchor, anchor + "\n" + rule + "\n", 1)


def patch_readme(text: str) -> str:
    if DOCUMENT_IMPACT_RULE not in text:
        if IMPACT_RULE_RE.search(text):
            text = IMPACT_RULE_RE.sub(DOCUMENT_IMPACT_RULE, text, count=1)
        else:
            timing = TIMING_RULE_RE.search(text)
            if not timing:
                raise ValueError("README: timing rule anchor not found")
            text = text[: timing.end()] + "\n\n" + DOCUMENT_IMPACT_RULE + text[timing.end() :]

    if DOCUMENT_RECORD_RULE not in text:
        if RECORD_RULE_RE.search(text):
            text = RECORD_RULE_RE.sub(DOCUMENT_RECORD_RULE, text, count=1)
        else:
            text = insert_rule_after_heading(
                text, "## 文档变更记录", DOCUMENT_RECORD_RULE, "document record"
            )

    if DOCUMENT_CONSISTENCY_RULE not in text:
        if CONSISTENCY_RULE_RE.search(text):
            text = CONSISTENCY_RULE_RE.sub(DOCUMENT_CONSISTENCY_RULE, text, count=1)
        else:
            text = insert_rule_after_heading(
                text, "## 阶段完成一致性收敛", DOCUMENT_CONSISTENCY_RULE, "consistency"
            )

    if README_VALIDATOR_PARAGRAPH not in text:
        validation_re = re.compile(
            r"验证器会要求每个 `SKILL\.md` 包含.*?(?=\n\n`evals/)",
            re.DOTALL,
        )
        if not validation_re.search(text):
            raise ValueError("README: validator description anchor not found")
        text = validation_re.sub(README_VALIDATOR_PARAGRAPH, text, count=1)
    return text


def validator_constant(name: str, value: str) -> str:
    parts: list[str] = []
    remaining = value
    while remaining:
        part, remaining = remaining[:100], remaining[100:]
        escaped = part.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'    "{escaped}"')
    return f"{name} = (\n" + "\n".join(parts) + "\n)"


def read_string_constants(text: str, names: set[str]) -> dict[str, str]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError(f"validator: invalid Python syntax: {exc}") from exc
    result: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in names:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"validator: {target.id} is not a literal string") from exc
        if isinstance(value, str):
            result[target.id] = value
    return result


def replace_validator_constant(text: str, name: str, value: str) -> str:
    block = validator_constant(name, value)
    pattern = re.compile(rf"{re.escape(name)} = \(\n.*?\n\)", re.DOTALL)
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    if name == "DOCUMENT_IMPACT_RULE":
        timing_pattern = re.compile(r"DOCUMENT_TIMING_RULE = \(\n.*?\n\)", re.DOTALL)
        match = timing_pattern.search(text)
        if not match:
            raise ValueError("validator: timing constant anchor not found")
        return text[: match.end()] + "\n\n" + block + text[match.end() :]
    raise ValueError(f"validator: {name} constant anchor not found")


def patch_validator(text: str) -> str:
    expected = {
        "DOCUMENT_TIMING_RULE": DOCUMENT_TIMING_RULE,
        "DOCUMENT_IMPACT_RULE": DOCUMENT_IMPACT_RULE,
        "DOCUMENT_CONSISTENCY_RULE": DOCUMENT_CONSISTENCY_RULE,
        "DOCUMENT_RECORD_RULE": DOCUMENT_RECORD_RULE,
    }
    actual = read_string_constants(text, set(expected))
    for name, value in expected.items():
        if actual.get(name) != value:
            text = replace_validator_constant(text, name, value)

    if 'CANONICAL_RECORD_WRITER = ROOT / "scripts" / "document_record.py"' not in text:
        anchor = 'SKILLS_DIR = ROOT / "skills"\n'
        if anchor not in text:
            raise ValueError("validator: skills-dir anchor not found")
        text = text.replace(
            anchor,
            anchor + 'CANONICAL_RECORD_WRITER = ROOT / "scripts" / "document_record.py"\n',
            1,
        )

    impact_check = (
        '    if DOCUMENT_IMPACT_RULE not in text:\n'
        '        errors.append("missing canonical structural-change impact propagation rule")\n'
    )
    if impact_check not in text:
        anchor = (
            '    if DOCUMENT_TIMING_RULE not in text:\n'
            '        errors.append("missing canonical stage-document update timing rule")\n'
        )
        if anchor not in text:
            raise ValueError("validator: timing-rule check anchor not found")
        text = text.replace(anchor, anchor + impact_check, 1)

    targeted_constant = (
        "TARGETED_RULE_MARKERS = {\n"
        '    "game-tech-clarify": "**跨边界通信合同硬限制：",\n'
        '    "game-scaffold": "**框架真实链路硬限制：",\n'
        '    "game-implement": "**真实消费链验证硬限制：",\n'
        '    "game-client-handoff": "**客户端合同可达性硬限制：",\n'
        "}\n"
    )
    if "TARGETED_RULE_MARKERS = {" not in text:
        anchor = 'REVIEW_BRANCH_FORBIDDEN_MARKER = "禁止创建 `07-Uxx-*`"\n'
        if anchor not in text:
            raise ValueError("validator: targeted marker insertion anchor not found")
        text = text.replace(anchor, anchor + "\n" + targeted_constant, 1)

    targeted_check = (
        "    targeted_marker = TARGETED_RULE_MARKERS.get(name)\n"
        "    if targeted_marker and targeted_marker not in text:\n"
        "        errors.append(\"missing targeted cross-layer contract/runtime-chain rule\")\n"
    )
    if targeted_check not in text:
        anchor = (
            '    if DOCUMENT_RECORD_RULE not in text:\n'
            '        errors.append("missing canonical document change record rule")\n'
        )
        if anchor not in text:
            raise ValueError("validator: record-rule check anchor not found")
        text = text.replace(anchor, anchor + targeted_check, 1)

    required_snippet = (
        '    bundled_writer = skill_dir / "scripts" / "document_record.py"\n'
        '    if not bundled_writer.is_file():\n'
        '        errors.append("missing bundled UTF-8 document record writer")\n'
        '    elif bundled_writer.read_bytes() != CANONICAL_RECORD_WRITER.read_bytes():\n'
        '        errors.append("bundled document record writer differs from canonical writer")\n'
    )
    if required_snippet not in text:
        anchor = (
            '    if DOCUMENT_RECORD_RULE not in text:\n'
            '        errors.append("missing canonical document change record rule")\n'
        )
        if anchor not in text:
            raise ValueError("validator: record-rule check anchor not found")
        text = text.replace(anchor, anchor + required_snippet, 1)
    return text


def write_text_if_changed(path: Path, new_text: str, *, check: bool) -> bool:
    old_text = path.read_text(encoding="utf-8")
    if old_text == new_text:
        return False
    if not check:
        path.write_text(new_text, encoding="utf-8", newline="\n")
    return True


def write_bytes_if_changed(path: Path, new_bytes: bytes, *, check: bool) -> bool:
    old_bytes = path.read_bytes() if path.exists() else None
    if old_bytes == new_bytes:
        return False
    if not check:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(new_bytes)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed: list[Path] = []
    try:
        writer_bytes = CANONICAL_WRITER.read_bytes()
        for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            old = skill_file.read_text(encoding="utf-8")
            new = patch_skill(old, skill_file)
            if write_text_if_changed(skill_file, new, check=args.check):
                changed.append(skill_file)

            bundled_writer = skill_file.parent / BUNDLED_WRITER_RELATIVE
            if write_bytes_if_changed(bundled_writer, writer_bytes, check=args.check):
                changed.append(bundled_writer)

        old_readme = README.read_text(encoding="utf-8")
        if write_text_if_changed(README, patch_readme(old_readme), check=args.check):
            changed.append(README)

        old_validator = VALIDATOR.read_text(encoding="utf-8")
        if write_text_if_changed(VALIDATOR, patch_validator(old_validator), check=args.check):
            changed.append(VALIDATOR)
    except (OSError, ValueError) as exc:
        print(f"policy application failed: {exc}", file=sys.stderr)
        return 2

    if changed:
        prefix = "NEEDS UPDATE" if args.check else "UPDATED"
        for path in changed:
            print(f"{prefix} {path.relative_to(ROOT)}")
        return 1 if args.check else 0

    print("Stage document policy is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
