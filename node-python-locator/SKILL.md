---
name: "[Harvest] Node环境Python运行时定位"
description: 在Office翻译技能中，当Node.js流水线需要调用Python脚本时，用于动态解析正确的Python可执行文件路径。解决因托管布局差异（如node/bin层级缺失）导致的硬编码路径失效问题，确保跨环境兼容性。
created_by: main_agent
---
## Workflow
1. **获取Node执行路径**：在Node.js脚本中使用 `process.execPath` 获取当前Node二进制文件的绝对路径。
2. **推导根目录**：根据预安装布局规范，从Node路径向上回溯至共同的父级目录（通常为 `{root}/pre-install/{hash}`）。注意处理 `node/bin/node` 与 `node/node` 两种常见层级差异。
3. **构建Python路径**：在推导出的根目录下，拼接标准Python子路径（如 `python/python.exe` 或 `bin/python`）。
4. **存在性验证**：使用 `fs.existsSync` 检查构建的路径是否有效。若无效，尝试备选路径（如直接检查PATH中的 `python` 命令）。
5. **执行调用**：将解析到的绝对路径传入 `spawnSync` 或 `execFile`，避免依赖环境变量或相对路径。

## Suggestions
- 优先使用 `fileURLToPath(import.meta.url)` 结合 `path.dirname` 定位技能根目录，再基于相对路径查找 Python，比依赖 `process.execPath` 更稳健。
- 在开发环境中，允许通过环境变量 `PYTHON_PATH` 覆盖自动检测结果，便于调试。

## Pitfalls
- **硬编码陷阱**：严禁在代码中写死 `../python/python.exe` 等相对路径，因为Node和Python在预安装包中的相对层级可能随版本更新而变化。
- **路径层级误判**：某些部署包中Node位于 `bin/` 子目录下，而Python位于同级目录，直接向上跳两级会导致路径错误。必须通过实际文件系统探测或配置元数据确认布局。
