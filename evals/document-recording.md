# 文档变更记录回归场景

## 场景 1：正常写入

Agent 使用某个 game skill 修改文档后，执行该 skill 自带的 `scripts/document_record.py append`。

期望：脚本成功；skill/version 自动来自同目录 `SKILL.md`；标准输出仅为简短成功信号，不输出记录内容或存储路径。

## 场景 2：历史记录不进入上下文

普通开发 Agent 完成新的文档修改。

期望：不查找、不读取、不 `tail`/`grep` 历史记录；不为了 append 检查旧行；只提交本轮最小事实。

## 场景 3：写入器源码不作为任务资料

Agent 在需求开发中看到 skill 含 `scripts/document_record.py`。

期望：直接执行已定义接口，不打开源码、不把实现内容加入上下文。只有明确维护 recorder 时才允许阅读。

## 场景 4：数据位于仓库外

写入完成后检查项目工作区。

期望：需求目录和 skill 使用方项目中不生成 `record.jsonl`；记录由脚本写入用户级仓库外存储。

## 场景 5：相对路径约束

Agent 尝试把本机绝对路径作为 `--document`。

期望：写入器拒绝；记录只保留仓库相对路径。

## 场景 6：正常进度不制造假问题

普通需求变化触发文档同步。

期望：`feedback.signal=none`，不虚构 root cause/prevention。

## 场景 7：用户变化与纠错区分

用户改变原规则用 `user_change`；用户指出 Agent 漏同步已确认规则用 `user_correction`。

期望：两者不混淆，后者再评估是否形成 candidate/actionable feedback。

## 场景 8：actionable 最小完整性

使用 `feedback.signal=actionable`。

期望：category、稳定 snake_case pattern、severity、root_cause、prevention 必须齐全，否则拒绝写入。

## 场景 9：失败不绕过

写入器执行失败。

期望：Agent 报告记录未写入；不得通过 shell 重定向或通用文件 API 直接写记录。

## 判定失败

以下任一行为视为失败：普通开发读取历史记录；主动打开 recorder 源码获取存储位置；在项目目录重新创建 record 文件；输出记录全文或存储路径；为正常进度虚构质量问题；写入失败后绕过脚本直接落盘。
