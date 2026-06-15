# 设计变更 change_2：Phase 1 review 发现的正文 heading 歧义

- 触发：Phase 1 四路 review（Claude Opus m5 指出）
- 日期：2026-06-13
- 结果：design v1.3 → v1.4
- 影响范围：§3.4 段落规则

## 问题
正文出现骨架外的额外 ## heading（如人随手加"## 备注"），当前实现一律 E_SCHEMA 打回。
但设计 §3.4 只说"section_credibility 的 key 不在骨架→打回"，没说正文额外 heading 要硬打回。
当前实现"正文必须恰好等于骨架"过严，会挡住人写补充小节。

## 决策（宽松）
- section_credibility 的 key 必须在骨架内（不在则打回）——不变
- 正文允许骨架外额外补充 heading，不打回
- 规则：正文 heading ⊇ 骨架核心段落（可多不可少）；section_credibility key ⊆ 骨架段落

## 处理
开发者确认宽松。design 升 v1.4。Codex 据此放宽正文 heading 校验（见 Phase 1 修复）。
