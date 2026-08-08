#!/usr/bin/env python3
"""安全审计分级与处置脚本（与 gitleaks + GitHub Actions 配套）。

用法:
  python3 scripts/security_audit.py --report gitleaks-report.json [--repo Sth32/skills] [--commit <sha>]

行为:
  - 读 gitleaks JSON report，按危险程度分级:
      P0 高危（真实凭据强规则命中）-> 钉钉告警 + 唤醒 CNB 打工人处置（撤销/移除/回退）
      P1 疑似（弱规则/敏感文件名）-> 钉钉告警，人工确认
      P2 无害（allowlist 命中 / 占位符 / 示例）-> 忽略
  - 无泄漏: 静默退出（exit 0）
  - 绝不把 Secret 值打印到日志或告警消息（只输出文件/行/规则/commit 定位信息）

环境变量:
  CNB_TOKEN         CNB OpenAPI 令牌（P0 时唤醒打工人用）
  DINGTALK_WEBHOOK  钉钉群机器人 webhook（含 access_token）
  DINGTALK_SECRET   钉钉机器人加签 secret

Allowlist 文件: .github/security-audit-allowlist.txt
  每行一条规则，支持前缀指令 + 正则:
    file:xxx   -> 正则匹配文件路径
    rule:xxx   -> 正则匹配 RuleID
    commit:xxx -> 正则匹配 commit sha
    match:xxx  -> 正则匹配泄漏上下文文本
    其他        -> 正则匹配文件路径
  空行和 # 注释忽略。命中 allowlist 的 finding 视为 P2，不告警。
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ALLOWLIST_PATH = ".github/security-audit-allowlist.txt"

# P0 强规则前缀：命中即视为真实凭据（高危）
P0_RULE_PREFIXES = (
    "github", "aws-", "aws_", "gcp-", "google-service-account", "google-oauth",
    "google-api-key", "azure", "private-key", "openssh", "slack", "discord",
    "openai", "anthropic", "gemini", "stripe", "paypal", "twilio", "telegram",
    "cloudflare", "digitalocean", "alibaba", "tencent", "npm-", "pypi",
    "rubygems", "nuget", "datadog", "grafana", "sentry", "okta", "databricks",
    "huggingface", "postgresql", "mysql-connection", "mongodb", "redis-connection",
    "shopify", "mailchimp", "sendgrid", "twitch", "dropbox", "bitbucket",
    "doppler", "fastly", "heroku", "facebook", "linkedin", "square",
    "pulumi", "terraform", "vault", "confluent", "snowflake", "auth0",
    "snyk", "vercel", "zeit", "vonage", "vitally", "webhook", "wechat",
    "codecov", "circle", "buildkite", "travis", "gitter", "gitlab", "hashicorp",
    "linear", "lob", "loggly", "logz", "mailgun", "mapbox", "maxmind",
    "messagebird", "microsoft-teams", "netlify", "new-relic", "nyc",
    "packagist", "pexels", "plaid", "postman", "prefect", "proctorio",
    "quay", "rabbitmq", "rapidapi", "razorpay", "readme", "remote-",
    "samsara", "scalingo", "segment", "sendinblue", "shippo", "sidekiq",
    "sidekiq-sensitive", "signal", "skylight", "snyk", "sonar", "sourcegraph",
    "splitwise", "spotify", "spring", "square", "stackhawk", "stripe",
    "sumologic", "t1shales", "teamcity", "telegram", "tines", "travis",
    "trello", "twilio", "twitter", "typeform", "ubiquiti", "urlscan",
    "vault", "versioneye", "virustotal", "webex", "weglot", "workos",
    "zendesk", "zulip",
)
# P1 弱规则（格式匹配但置信度低，需人工确认）
P1_RULE_IDS = {"generic-api-key", "jwt", "secret-key-pattern", "aws-account-id"}

# 占位符/示例标记：命中视为无害（P2）
PLACEHOLDER_RE = re.compile(
    r"(example|xxx+|your[-_][a-z]+|changeme|placeholder|dummy|fake|sample|"
    r"test[-_]?token|aaaa+|<\S+>|password[:=]password|redacted)",
    re.I,
)

# 敏感文件名：提交即告警（P1），不依赖 gitleaks 规则
SENSITIVE_FILE_RE = re.compile(
    r"(^|/)\.env($|\.)|credential|id_rsa|\.pem$|\.key$|\.p12$|\.pfx$|\.jks$|"
    r"\.npmrc$|(^|/)\.netrc$|service-account|firebase[-_.]|keystore|"
    r"(^|/)[^/]*token[^/]*$",
    re.I,
)
# 示例/测试/文档目录：敏感文件名命中但在此路径下则忽略
EXCLUDE_PATH_RE = re.compile(r"(example|sample|test|spec|fixture|docs?/|template)", re.I)


def load_report(path):
    if not os.path.exists(path):
        print(f"[error] report 文件不存在: {path}")
        return []
    with open(path) as f:
        data = json.load(f)
    # gitleaks v8 顶层是数组；旧版是 {"Findings": [...]}，两者都兼容
    if isinstance(data, list):
        return data
    return data.get("Findings", [])


def load_allowlist(path):
    patterns = []
    if not os.path.exists(path):
        return patterns
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("file:"):
                patterns.append(("file", re.compile(line[5:], re.I)))
            elif line.startswith("rule:"):
                patterns.append(("rule", re.compile(line[5:], re.I)))
            elif line.startswith("commit:"):
                patterns.append(("commit", re.compile(line[7:], re.I)))
            elif line.startswith("match:"):
                patterns.append(("match", re.compile(line[6:], re.I)))
            else:
                patterns.append(("file", re.compile(line, re.I)))
    return patterns


def allowlist_hit(finding, allowlist):
    for kind, pat in allowlist:
        target = {
            "file": finding.get("File", ""),
            "rule": finding.get("RuleID", ""),
            "commit": finding.get("Commit", ""),
            "match": finding.get("Match", ""),
        }.get(kind, "")
        if pat.search(target):
            return True
    return False


def is_placeholder(finding):
    # 只检查 Secret 值本身（真实随机密钥几乎不可能含 example/xxx 字样；
    # 用 Match 上下文判断会把"值旁边有示例文字"的真实密钥误降级）
    return bool(PLACEHOLDER_RE.search(finding.get("Secret", "")))


def classify(finding, allowlist):
    """返回 P0 / P1 / P2"""
    if allowlist_hit(finding, allowlist):
        return "P2"
    rule = finding.get("RuleID", "")
    if is_placeholder(finding):
        return "P2"
    if rule.startswith(P0_RULE_PREFIXES):
        return "P0"
    return "P1"


def scan_sensitive_files():
    """git ls-files 中找敏感文件名（.env / credentials / 私钥等）"""
    try:
        out = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, timeout=30
        ).stdout
    except Exception:
        return []
    hits = []
    for path in out.splitlines():
        if EXCLUDE_PATH_RE.search(path):
            continue
        if SENSITIVE_FILE_RE.search(path):
            hits.append(path)
    return hits


def dingtalk_send(title, text, msgtype="markdown"):
    webhook = os.environ.get("DINGTALK_WEBHOOK", "")
    secret = os.environ.get("DINGTALK_SECRET", "")
    if not webhook or not secret:
        print("[warn] 缺少 DINGTALK_WEBHOOK/DINGTALK_SECRET，跳过钉钉告警")
        return False
    ts = str(int(time.time() * 1000))
    string_to_sign = f"{ts}\n{secret}"
    sign = urllib.parse.quote_plus(
        base64.b64encode(
            hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
        )
    )
    url = f"{webhook}&timestamp={ts}&sign={sign}"
    payload = {"title": title, "text": text}
    body = json.dumps({"msgtype": msgtype, msgtype: payload}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        if resp.get("errcode") != 0:
            print("[warn] 钉钉发送失败:", resp)
            return False
        print("[ok] 钉钉告警已发送:", title)
        return True
    except Exception as e:
        print("[warn] 钉钉发送异常:", e)
        return False


def wake_worker(repo, commit, findings):
    """P0 时唤醒 CNB 打工人：撤销密钥 + 移除泄漏 + 钉钉汇报"""
    cnb_token = os.environ.get("CNB_TOKEN", "")
    if not cnb_token:
        print("[warn] 缺少 CNB_TOKEN，无法唤醒打工人")
        return None
    detail_lines = []
    for f in findings[:20]:
        detail_lines.append(
            f"- {f.get('File','?')}:{f.get('StartLine','?')} "
            f"[{f.get('RuleID','?')}] commit {f.get('Commit','?')[:12]}"
        )
    detail = "\n".join(detail_lines)
    task = f"""GitHub 仓库 {repo} 安全审计发现【高危密钥泄漏】，请立即处置。

【泄漏详情】（commit {commit[:12]}，共 {len(findings)} 处）
{detail}

【处置步骤】
1. 克隆仓库（用已注入的 GITHUB_TOKEN 环境变量）:
   git clone https://x-access-token:$GITHUB_TOKEN@github.com/{repo}.git audit && cd audit
2. 逐条核实泄漏是否真实（打开文件看内容）:
   - 若是占位符/示例/测试值 -> 跳过，不算泄漏
   - 若是真实密钥:
     a. GitHub 生态 token（PAT/SSH key/OAuth）: 当前令牌无法用 API 撤销（fine-grained PAT 无撤销接口），
        在钉钉汇报里明确列出，请用户到 github.com/settings/tokens 手动撤销
     b. 云厂商/第三方密钥: 同样无法自动撤销，钉钉汇报里列明，请用户到对应控制台撤销
     c. 无论能否撤销，都要从仓库移除泄漏内容（git rm 文件或编辑删除密钥行），
        不要重写历史（历史已泄露，force-push 重写意义有限且有风险）
3. 提交并推送修复:
   git add -A
   git commit -m "[ci-skip-notify] security: remove leaked secret"
   git push origin main
   （commit 消息必须以 [ci-skip-notify] 开头，否则审计 workflow 会再次触发造成死循环）
4. 验证: 重新拉取后确认泄漏内容已不在工作区文件里（不必重跑完整审计）。
5. 钉钉汇报（必须做）:
   环境变量 DINGTALK_WEBHOOK / DINGTALK_SECRET 已注入。
   加签算法: timestamp=当前毫秒; string_to_sign=timestamp+"\\n"+DINGTALK_SECRET;
   sign=base64(hmac_sha256(string_to_sign, DINGTALK_SECRET)) 并 URL 编码;
   请求 URL = DINGTALK_WEBHOOK + "&timestamp=" + timestamp + "&sign=" + sign
   用 msgtype=markdown，内容包含: 泄漏位置、核实结论、已移除的文件、需要用户手动撤销的密钥清单。
6. 遇到不确定的情况（疑似误报/需要设计决策）-> 钉钉发"需人工确认"并停手，不要乱改仓库。

完成后用简洁中文总结你的操作。"""
    body = json.dumps(
        {
            "event": "api_trigger_npc",
            "npc": {"name": "CodeBuddy", "workMode": True},
            "env": {
                "systemPrompt": "你是 CodeBuddy，自主编程打工人。收到任务后直接动手执行，完成后用简洁中文总结。",
                "userPrompt": task,
            },
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.cnb.cool/qun-org/worker/-/build/start",
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + cnb_token,
            "Content-Type": "application/json",
        },
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
        sn = resp.get("sn", resp)
        print("[ok] 打工人已唤醒:", sn)
        return sn
    except Exception as e:
        print("[warn] 唤醒打工人失败:", e)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="gitleaks-report.json")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "unknown/repo"))
    ap.add_argument("--commit", default=os.environ.get("GITHUB_SHA", "unknown"))
    args = ap.parse_args()

    findings = load_report(args.report)
    allowlist = load_allowlist(ALLOWLIST_PATH)

    p0, p1, p2 = [], [], []
    for f in findings:
        level = classify(f, allowlist)
        (p0 if level == "P0" else p1 if level == "P1" else p2).append(f)

    sensitive_files = [
        p for p in scan_sensitive_files() if not any(p == x for x in [])
    ]

    print(f"gitleaks findings: {len(findings)} (P0={len(p0)} P1={len(p1)} P2={len(p2)})")
    for f in p0:
        print(f"  [P0] {f.get('File','?')}:{f.get('StartLine','?')} {f.get('RuleID','?')} commit={f.get('Commit','?')[:12]}")
    for f in p1:
        print(f"  [P1] {f.get('File','?')}:{f.get('StartLine','?')} {f.get('RuleID','?')} commit={f.get('Commit','?')[:12]}")
    for f in p2:
        print(f"  [P2-忽略] {f.get('File','?')}:{f.get('StartLine','?')} {f.get('RuleID','?')}")
    if sensitive_files:
        print(f"敏感文件名: {len(sensitive_files)} 个")
        for p in sensitive_files:
            print(f"  [!] {p}")

    if not p0 and not p1 and not sensitive_files:
        print("✓ 未发现需要告警的泄漏")
        return 0

    # 钉钉告警
    commit_short = args.commit[:12]
    loc_lines = []
    for f in p0 + p1:
        loc_lines.append(
            f"| `{f.get('File','?')}` | {f.get('StartLine','?')} | "
            f"`{f.get('RuleID','?')}` | `{f.get('Commit','?')[:12]}` |"
        )
    loc_table = "\n".join(loc_lines)
    extra = ""
    if sensitive_files:
        extra = "\n\n**敏感文件已提交（建议确认）**:\n" + "\n".join(
            f"- `{p}`" for p in sensitive_files
        )

    if p0:
        text = (
            f"## 🚨 高危密钥泄漏\n\n"
            f"**仓库**: {args.repo}  \n**commit**: `{commit_short}`  \n"
            f"**时间**: {time.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"### 泄漏清单（P0，共 {len(p0)} 处）\n"
            f"| 文件 | 行 | 规则 | commit |\n|---|---|---|---|\n{loc_table}\n"
            f"\n**处置**: 已自动唤醒 CNB 打工人撤销/移除密钥，完成后另行汇报。"
            f"请留意后续消息，并按汇报要求手动撤销无法自动撤销的密钥。{extra}"
        )
        dingtalk_send(f"🚨 高危密钥泄漏 {args.repo}", text)
        wake_worker(args.repo, args.commit, p0)
    else:
        text = (
            f"## ⚠️ 疑似凭据泄漏（需人工确认）\n\n"
            f"**仓库**: {args.repo}  \n**commit**: `{commit_short}`  \n"
            f"**时间**: {time.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"### 疑似清单（P1，共 {len(p1)} 处）\n"
            f"| 文件 | 行 | 规则 | commit |\n|---|---|---|---|\n{loc_table}\n"
            f"\n**处置**: 请人工确认是否为真实密钥。若为误报，"
            f"将对应文件/规则加入 `.github/security-audit-allowlist.txt`。{extra}"
        )
        dingtalk_send(f"⚠️ 疑似凭据泄漏 {args.repo}", text)

    return 1


if __name__ == "__main__":
    sys.exit(main())
