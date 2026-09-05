# AGENTS.md

原则：简洁、高效，以解决问题为选择方案的第一要素。不为个别文件写一次性补丁脚本，优先修 skill 本体。本目录是该项目的唯一目录。

## 项目定位

ZCode 翻译 skill：专业翻译 Office 文件（Word/Excel/PPT），保留版式、术语、公式、图片与可编辑性。根 `SKILL.md` 只做路由，按扩展名分发到 `formats/<word|excel|ppt>/SKILL.md`，路由后不得跨适配器。

## 目录

- `formats/{word,excel,ppt}/` — 各自的 `SKILL.md`（流程契约）、`scripts/`、`references/`（工作流文档，改行为必须同步改）、`tests/`
- `references/水泥专业名词中英对照.md` — 共享词汇表（有哈希契约测试）
- `tests/` — 跨技能测试（路由契约、skill 结构、word 管线）
- `docs/superpowers/` — 设计方案与规格
- `jobs/` — 历史作业产物（docx/pdf 等，勿删）；`work/` — 作业运行状态（已 gitignore）

## 本机环境（不在 PATH 上）

- Node: `C:\Users\AGICO\tools\node22\node-v22.14.0-win-x64\node.exe`
- Python: `C:\Users\AGICO\AppData\Local\Programs\Python\Python312\python.exe`（无 pytest，用 unittest）
- `@oai/artifact-tool`（exceljs 兼容 shim）源码在仓库 `vendors/artifact-tool/`（受版本控制，勿删）；运行时经两级 junction 解析：仓库根 `node_modules` → `C:\Users\AGICO\node_modules`（exceljs 装在这里）→ `@oai\artifact-tool` junction 指回仓库 vendors。junction 被清理会直接导致 Excel 管线瘫痪，重建命令见"常用命令"
- 管线传参：`--node-path` + `--node-modules`，或设 `CODEX_NODE` / `CODEX_PYTHON`

## 常用命令

```bash
# Excel 管线测试（node）
CODEX_PYTHON="<python.exe>" <node.exe> --test formats/excel/tests/test_excel_pipeline.mjs
# Excel Python 测试 / 根目录测试
python -m unittest discover -s formats/excel/tests -p "test_*.py"
python -m unittest discover -s tests -p "test_*.py"
```

```bash
# 重建 node_modules junction（被清理后必须重建，否则 Excel 管线无法运行）
cmd /c "mklink /J E:\office-translate-pro\node_modules C:\Users\AGICO\node_modules"
cmd /c "mklink /J C:\Users\AGICO\node_modules\@oai\artifact-tool E:\office-translate-pro\vendors\artifact-tool"
# 重装 exceljs（如 C:\Users\AGICO\node_modules 被清空）
<node.exe> <node>\node_modules\npm\bin\npm-cli.js install exceljs --prefix C:\Users\AGICO --registry https://registry.npmmirror.com
```

Excel 翻译作业：`formats/excel/scripts/excel_fast_pipeline.py prepare|finalize --node-path ... --node-modules ...`，作业目录放 `work/`。交付门禁 = `verify` + `office-validate`（真实 Excel COM，`excel_com_verify.ps1`）都通过；禁止导出 PDF、禁止 LibreOffice、禁止额外视觉门禁。

## 已知坑

1. **`sync.ps1` 会用 GitHub 上游 zip 镜像覆盖本目录**（robocopy /MIR）。本地 git 历史与上游无关联且有未推送提交，**未推送前严禁运行 sync.ps1**，否则本地提交丢失。
2. 根目录 `node_modules` 是 junction，勿删；`.gitignore` 和 `sync.ps1` 的 `/XD node_modules` 已防护，改 sync.ps1 时保留。
3. git 身份是仓库级占位（AGICO / AGICOGROUP@users.noreply.github.com），提交前按需改。
4. 文件名常含中文/西里尔文：命令行传参用正斜杠 + 引号。
5. 仓库级工作改动提交后，注意 `C:\Users\AGICO\.zcode\skills\office-translate-pro` 是旧部署副本，需单独同步才在其他工作区生效。
6. 改 Excel 双语行为前必读 `formats/excel/SKILL.md` 与 `formats/excel/references/bilingual-row-layout.md`；双语行倍增的几何约束见 `excel_pipeline.mjs` 的 `buildBilingualWorkbook`（纵向合并重建为逐行横向条带）。
