# 维护 Skill（行为契约）

防知识腐烂。排查闭环的必经步骤（非顺手做）。

## 强制维护检查点（输出最终诊断前）
1. search_kb 查相关条目
2. 对比 code_binding（git_sha/paths/symbols）与当前代码
3. 不一致→propose_update 标 stale=true + stale_reason
4. 把维护动作写进诊断报告（"已检查 N 条，标记 M 条 stale"，可审计）

## 标 stale 判断
- 相关 paths/symbols 确实变了→标；只是仓库整体 sha 变但相关路径没动→不标（避免误报）；拿不准→标+"待人工复核"。

## 不要
不直接改 published（只能 propose_update 走审）/ 不因仓库 sha 变就批量标。
