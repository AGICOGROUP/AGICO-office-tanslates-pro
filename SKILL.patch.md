## Patch 2026-09-22 11:06

Step 3 (Write): `formats/excel/scripts/excel_native_ooxml.py` 的 `write_cell` 逻辑存在两项实质缺陷：
1. **强制换行破坏布局**：原逻辑对译文长度超过列宽的单元格自动启用 `wrapText` 并撑高行高。这摧毁了 Excel 默认的“文本溢出到右侧空单元格”机制，导致工程数据表标签出现大量非预期折行。**修正**：仅当源单元格本身已开启 `wrapText` 时才在输出中保留该属性；否则保持默认，允许文本自然溢出。
2. **富文本字号压平**：原逻辑将包含多字号混排（rich-text runs）的源单元格改写为纯文本 inline string，导致视觉字号不一致。**修正**：检测源单元格的 `<r>` 节点，若存在则克隆其结构并仅替换文本内容，保留原有的 `sz`、`rFont` 等格式属性。
## Patch 2026-09-22 11:11

Step 3 (Write): 修正 `excel_native_ooxml.py` 的行高处理逻辑。原逻辑无条件对含译文单元格启用 `wrapText` 并撑高行高，破坏了 Excel 默认的文本溢出机制。新逻辑：仅当源单元格已开启 `wrapText` 时才保留该属性；否则保持默认，允许文本自然溢出至右侧空单元格。

Tests: 同步更新 `test_excel_native_ooxml.py` 断言。移除对“写入器自动撑高第1行”的旧有依赖，改为验证在无 `wrapText` 样式下行高保持不变，以及富文本字号结构在替换后得以保留。

## Patch 2026-09-22 — 单语替换的版式不变量：保真源换行模式，而非强制换行

`formats/excel/scripts/excel_native_ooxml.py` 原先把"译文超出列宽就必须有 `wrapText`"当作正确性规则，
写入器 `expand_layout()` 据此**克隆样式并注入 `wrapText="1"`**，同时按 `lines*15+3` **撑高行**；
校验器 `style-change:missing-wrap` 与行高掩码（对任何含译文单元的行无条件放行 `ht`/`customHeight`）
共同把该行为锁成契约。

这是设错的不变量。工程数据表的长标签依赖 Excel 默认行为——**不换行的文本可溢出到右侧空单元格**。
一旦注入 `wrapText`，溢出被摧毁，文本被迫在列宽内折行，于是译文出现作者从未要求的视觉换行与更高行距。
实测该表：`wrapText` 单元格 36→55（注入 19 个），18 行行高被改（如 28.15→48）。

**现行不变量**（写入器与校验器必须同时满足）：
- 源单元格未换行 → 译文保持未换行，样式与行高逐字不变。
- 源单元格已换行 → 保留 `wrapText`，允许按译文长度增加行高。
- 校验器改为双向检出：`style-change:lost-wrap`（丢失原有换行）与
  `style-change:injected-wrap`（注入原本没有的换行）。
- 行高掩码只对"源样式本就换行"的行（`growable_rows`）生效，其余行高变化即为结构损坏。

回归：`test_rich_shared_strings_split_and_all_other_parts_survive` 断言改为行高保真且样式表无 `wrapText`；
`test_verifier_detects_rich_properties_and_style_association_damage` 的 `s="1"` 篡改向量因写入器不再克隆
换行样式而失效，改用越界样式索引；新增
`test_verifier_rejects_injected_wrap_and_row_growth_on_unwrapped_cells`。

**双语模式不适用本规则**：`excel_bilingual_ooxml.py` 把原文与译文放入同一单元格，换行是必要的，
其 `wrapText`/`customHeight` 逻辑保持原样。

## Patch 2026-09-22 — 图内文字改为「双方法可选」：生成式编辑 与 确定性擦除回填

** operative 变更**：`references/image-translation.md` 新增 *Two accepted methods* 选择表；
根 `SKILL.md`、`formats/word/SKILL.md`、`formats/excel/SKILL.md`、`formats/ppt/SKILL.md` 及
excel/ppt 的 `image-text-localization.md` 中所有「`image_edit` 是唯一方法」的断言已全部改写为
按图选择。算法沉淀为新脚本 `scripts/inimage_erase_refill.py`（`ocr` / `render` / `verify` / `zoom`）。

**为什么必须保留第二条路径**（实测两张螺旋输送机工程图，1881×926 与 1571×847）：

| 指标 | 生成式 `image_edit` | 确定性擦除回填 |
|---|---|---|
| 标签框外强边缘保留 | 21.5% | 100.0% |
| 标签框外像素改动 | 整幅重绘 | 0.000% |

原文还写着「programmatic label drawing 已退役，因为反复通不过排版冲突与遮挡检查」——该结论把
一次性覆盖式贴图当成了唯一的程序化做法，否掉了整条逐像素擦除路线，属于与自身契约冲突的过度守卫。

**硬约束（防回退）**：
1. 任何 operative 文档不得再出现「the only method / only GPT image editing」；由
   `tests/test_skill_structure.py::InImageMethodPolicyTests` 强制（`docs/` 归档计划除外）。
2. `verify` 未给出 `outside_changed_pct`≈0 且 `outside_edges_retained_pct`=100 之前，
   不得登记 `localized`。非零即坐标或表序有误，修表而不是放弃方法。
3. 保真度必须按框内/框外分别度量。把有意擦掉的文字算作"边缘丢失"会得出 48.6%/31.1% 的假失败。
4. 斜排/旋转标签若其轴对齐框必然罩住承载信息的图形，**保留原文并记录原因**；
   曾尝试「底色→笔画色」色相门控救它，全局中性但该框主色被深橙描边带偏导致英文残留，已回退，勿再引入。
5. `_drop_straight_lines` 必须在 `_dilate` **之前**执行：先膨胀会并掉粗体字母 1–2px 间隙，
   整行被误判为边框线跳过，源英文会存活在新译文下面。

`[Harvest] 图像局部网格化放大分析` 技能已下线，其放大复核步骤改由本技能 `zoom` 子命令承担。
