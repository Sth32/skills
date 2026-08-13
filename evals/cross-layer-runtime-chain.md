# 跨层真实消费链回归场景

## 目标

验证 `game-tech-clarify`、`game-scaffold`、`game-implement` 和 `game-client-handoff` 能把“定义存在”与“真实可达/真实消费”区分开，避免把 review 变成唯一兜底。

## 场景 1：内部 Host/View 被误当客户端合同

代码中存在 `ArmyHostView`，用于服务端线程/实体寻址；客户端同步 Schema 中没有对应可见字段。

期望：

- 03 的合同矩阵把它标为内部路由，不推断为客户端可见；
- 05 不把该 View 当成客户端同步骨架；
- 客户端对接文档不得声称客户端能直接读取；
- 若证据不足则明确写“未确认/缺口”。

## 场景 2：服务端有方法，但客户端 RPC 不可达

服务端类存在 `RequestJoinLegion()`，单元测试可直接调用，但没有客户端 Def/生成协议/RPC 注册。

期望：

- “方法存在”不能作为客户端能力证据；
- 05 至少追踪：定义/Schema → 生成或注册 → 路由 → 权威实体；
- handoff 只有在完整客户端可见路径存在时才能列为可调用 RPC；
- 缺少注册/生成物时保持未完成。

## 场景 3：配置字段已定义但运行时无人消费

Excel/Schema 中新增 `cooldown_seconds`，导表成功，代码没有任何运行时读取点。

期望：

- scaffold 不能仅凭导表成功宣称接入；
- 至少定位预期真实消费入口；
- implement 必须证明配置真源 → 生成/加载 → 运行时读取 → 行为生效；
- 若没有消费点，记录为实现缺口。

## 场景 4：授权对象与执行对象不一致

请求先对 entity A 做权限检查，随后根据不稳定 ID 再查一次并对 entity B 执行副作用。

期望：

- implement 追踪“权限检查对象 → 最终执行对象”；
- 必须证明二者身份绑定或在执行前重新验证；
- 不能只因为权限函数返回 true 就判定闭环。

## 场景 5：旧异步回包覆盖新命令

玩家发出命令 C1，随后发出 C2；C1 的异步回包更晚到达并覆盖 C2 状态。

期望：

- implement 检查 request/version/token 或等价时序保护；
- stale callback 必须被拒绝或验证为无害；
- 推荐 feedback pattern：`stale_async_callback_overwrite`。

## 场景 6：生命周期终态没有封口

目标实体可能进入 `closing`、被删除或超时；主流程只处理成功与普通失败。

期望：

- implement 检查当前功能实际相关的 target missing/closing/expire/timeout；
- 每个终态都必须明确副作用、回包和状态收敛；
- 不允许永久 pending 或重复结算。

## 场景 7：同一时间事实混用不同 clock

过期判断一处使用 wall clock，另一处使用 monotonic/tick，重启恢复又使用持久化绝对时间。

期望：

- 03/06 明确该时间事实的权威语义；
- implement 验证比较双方使用兼容时钟；
- 重启恢复路径与运行时路径不能因时钟域不同产生跳变。

## 场景 8：rollback 只有文档口号

06 写“异常时可回滚”，但没有开关、版本降级、数据兼容或明确执行步骤。

期望：

- implement 不把文字描述视为可执行回滚；
- 当前功能确实需要 rollback 时，必须有可验证执行路径；
- 否则明确风险或范围外，不写“已具备回滚”。

## 场景 9：Review 发现上述任一通用缺陷

期望：

- review 仍应报告问题；
- 同时把“为什么更早阶段没有防住”转成 candidate/actionable feedback；
- category 指向最靠近根因的 skill/eval/template/agent_execution；
- 补回归场景后，不能只在 review 文案里追加一条提醒。

## 判定失败

以下任一行为失败：

- 用类型、字段、方法“存在”代替真实可达/消费证据；
- 把内部服务端路由结构推断为客户端合同；
- 配置只验证定义与导表，不验证运行时消费；
- 权限检查对象和最终执行对象可能漂移却不检查；
- 不处理 stale async callback、目标生命周期终态或时钟一致性；
- rollback 无执行证据仍宣称闭环；
- review 重复发现同类问题却没有形成 skill/eval 学习信号。
