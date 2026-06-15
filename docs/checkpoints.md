# Checkpoints 登记

> 每个 Phase 完成打 tag 后在此登记（R3）。格式：tag | commit | 覆盖范围 | 回退指令 | 回退后状态

| tag | commit | 覆盖范围 | 回退指令 | 回退后状态 |
|-----|--------|----------|----------|------------|
| `checkpoint/phase_1_content_core` | `3751bcea2a18f3d1449e8433822d782e0eac58ec` | Phase 1 内容核、Pydantic schema、证据映射/校验、SQLite 发号与重建、三态目录一致性、code_binding shape-only 校验、dev_memory 三件套；PR #1 四路 review/R14 闭环，`48 passed`，coverage `96.84%`。 | `git switch main && git reset --hard checkpoint/phase_1_content_core` | 回到 Phase 1 合并完成、Phase 2 尚未开始的基线。 |
