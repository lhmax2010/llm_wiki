# Hash 口径规范（code_binding 用）

> design.md 附录 C 标为 P1 前置。本文件定义 code_binding 里三个 hash/id 的生成规则，
> 确保各 agent / 脚本 / 离线 stale 检测算出的 hash 一致（否则 stale 检测失真）。

## 背景

code_binding 用于把一条知识绑定到具体代码版本，stale 检测靠比对 hash 判断"代码变了没"。
关键约束：**同一份代码，任何工具任何时候算出的 hash 必须相同**。所以口径必须冻结。

---

## 1. path_hash（文件内容 hash）

**定义**：被绑定文件的**内容** hash，用于判断"这个文件变了没"。

```
path_hash = SHA-256( 文件原始字节内容 )
```

规则：
- 取**文件原始字节**（不做编码转换、不规范化换行符）——避免跨平台 CRLF/LF 导致 hash 不一致
- 算法 SHA-256，输出 hex 小写
- 存储格式：`{相对路径: hash}`，路径用**仓库根的相对路径 + 正斜杠 `/`**（不用反斜杠，跨平台一致）

示例：
```yaml
code_binding:
  path_hashes:
    "unipicture/decoder.c": "a3f8b2c1...（64 位 hex）"
```

> 注：path_hash 对整个文件内容敏感——文件任何改动（含注释、空行）都会变。
> 这是有意的：宁可多报 stale 待人复核，不可漏报。精细到符号级用 symbol_hash。

---

## 2. symbol_hash（符号级 hash）

**定义**：被绑定的**具体函数/符号**的 hash，比 path_hash 精细——只有该符号变了才 stale，
文件里其他无关函数改动不触发。

```
symbol_hash = SHA-256( 规范化后的符号定义文本 )
```

规则（C/C++，V1 主语言）：
- 用 **clangd / tree-sitter** 解析出符号（函数/方法）的**定义区间**（签名 + 函数体）
- 规范化：去掉前导/尾随空白、统一缩进为单空格、去掉注释（注释改动不算符号变）
- 对规范化后的文本算 SHA-256，hex 小写
- 存储：`{符号名: hash}`

示例：
```yaml
code_binding:
  symbols: ["decode_hdr_frame"]
  symbol_hashes:
    "decode_hdr_frame": "b7e4d9a2...（64 位 hex）"
```

**多语言降级（design §5.4）**：
- C/C++：clangd/tree-sitter 解析符号，算 symbol_hash
- 其他语言（V1 不主力支持）：**fallback 到 path_hash**（文件级，粗但可用），symbol_hashes 留空
- fallback 时在 code_binding 标记 `symbol_resolution: "fallback_path"`，让 stale 检测知道精度

---

## 3. build_config_id（构建配置标识）

**定义**：标识"这条知识在什么构建配置下成立"——同一代码不同构建配置（target/优化级/宏定义）
行为可能不同，所以要绑构建配置。

```
build_config_id = SHA-256( 规范化的关键构建参数 )[:16]   # 取前 16 位即可，不需全长
```

规则——关键构建参数包含（按固定顺序拼接，避免顺序导致 hash 不同）：
1. target 架构（如 `armv7l`）
2. 优化级（如 `-O2` / `-Os`）
3. 关键宏定义（影响该模块的 `-D` 宏，排序后拼接）
4. build type（如 `release` / `debug`）

拼接格式（固定顺序，用 `|` 分隔）：
```
arch=armv7l|opt=-Os|build=release|defines=ENABLE_HDR=1,USE_NEON=1
```
对这个字符串算 SHA-256 取前 16 hex。

存储：
```yaml
code_binding:
  build_config_id: "arm-os-release"   # 人可读别名（可选）
  build_config_hash: "3f8a2b1c9d4e5f6a"  # 16 位 hex（机器比对用）
```

> V1 简化：如果项目暂时只有一种构建配置，build_config_id 可用固定别名（如 "default"），
> build_config_hash 仍按上述算。等出现多配置再严格区分。

---

## 4. stale 检测逻辑（怎么用这些 hash）

离线脚本 `scripts/kb_health_check`（design §5.4，KB 外部工具）按此判断：

```
对每条 code_flow/log_baseline 知识：
  1. 取当前代码，按本规范重算 path_hash / symbol_hash
  2. 与 code_binding 里存的 hash 比对：
     - symbol_hash 存在且变了 → 标 stale（精确：该符号变了）
     - symbol_hash 不存在（fallback）但 path_hash 变了 → 标 stale（粗：文件变了）
     - 都没变 → 不 stale
  3. build_config_hash 与当前构建配置不符 → 标记"配置不匹配，待复核"
  4. 最终是否 stale 仍由人/agent 确认（脚本只提候选）
```

---

## 5. 冻结说明

- 算法：一律 SHA-256，hex 小写
- 路径：仓库根相对路径 + 正斜杠
- 字节口径：path_hash 取原始字节（不转码不规范换行）；symbol_hash 取规范化文本（去注释/统一空白）
- 这些口径冻结后**不得随意改**——改了会导致历史 hash 全部失配、全库误报 stale。
  如需改，走 R1 设计变更流程，并规划全库 hash 重算。
