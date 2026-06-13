# 入库 Skill（行为契约）

KB 下发给任意接入 agent 的入库契约。通用 markdown，任何 agent 加载后按此投稿。

## 步骤
1. **查重**：search_kb(query, expand_synonyms=true)。有相似→propose_update。
2. **判 entry_type**：defect_case/triage_rule/code_flow/log_baseline。你是生产者就直接填（你本就知道是哪类）。
3. **按段落骨架整理**（design §3.4）。
4. **填检索字段**：symptom_keywords（含同义说法）/error_codes（原文）/log_signatures/aliases。
5. **标可信度——给证据不凭空声明**：按决策树提供 evidence，claim_type 由证据映射（接口校验，会查文件存在）。
   ```
   有运行日志/复现→fact（附 log/repro）；读代码推导→static_inference（附 code: filepath+line）；
   见过类似→historical_pattern；LLM 推测→llm_hypothesis；规范→spec（附 ref+version）
   ```
   精确字段（error_code/git_sha）只原文引用，引不到留空+OPEN，绝不编造。
6. **段落级可信度**：关键段（根因/方案）建议单独标 section_credibility，不标则继承 entry 级。
7. **缺字段一次性问全**（不来回挤牙膏）。
8. **调接口**：propose_entry(draft, credibility, request_id)。处理返回的 warnings（被降级）/errors（打回）。

## 不要
不编造精确字段 / 不直接声明高 claim_type 而不给证据 / 不跳过查重 / 不碰 research 创建（agent 沉淀走正式 propose）。
