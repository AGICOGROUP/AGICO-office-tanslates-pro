---
name: "[Harvest] Word翻译图片尺寸与纵横比校验"
description: 用于在Office Translate Pro的Word适配流程中，确保本地化生成的图表满足严格的像素级验收标准。适用于解决“缺少源像素尺寸”或“纵横比不匹配”导致的图片被拒问题，通过精确计算整数倍缩放和填充来生成合规的最终资产。
created_by: main_agent
---
## Workflow
1. **获取源图精确尺寸**：在处理任何包含文本的图表前，必须使用图像处理库（如PIL）读取源文件的原始像素宽和高 `{source_width}` x `{source_height}`。严禁依赖元数据估算，必须获得确切的整数值。
2. **执行初始本地化编辑**：调用图像编辑工具生成包含目标语言文本的中间版本 `{generated_image}`。记录其输出尺寸 `{gen_width}` x `{gen_height}`。
3. **计算最小整数倍缩放因子**：为确保不丢失细节且满足纵横比要求，计算缩放因子 `k`。`k` 必须是满足 `k * source_width >= gen_width` 且 `k * source_height >= gen_height` 的最小正整数。若 `k < 1`，则强制 `k = 1`。
4. **生成最终合规资产**：将中间版本图像缩放到 `{final_width} = k * source_width` 和 `{final_height} = k * source_height`。如果缩放后仍有微小偏差，使用透明或背景色填充边缘，确保最终文件的像素尺寸严格等于 `{final_width}` x `{final_height}`。
5. **提交决策并验证**：在 `images-decisions.json` 中为对应图片ID填入 `source_width` 和 `source_height`。运行适配器脚本提交决策。若返回错误“localized Word image needs positive source pixel dimensions”，检查步骤1；若返回“generated image must preserve the exact source aspect ratio”，检查步骤3-4的计算逻辑。

## Suggestions
- 在批量处理多张图表时，可以编写一个Python脚本自动遍历图片文件夹，一次性完成所有源尺寸读取和 `k` 值计算，避免逐个手动查询。
- 如果源图本身不是标准矩形或有复杂边框，建议先裁剪出核心内容区域再计算尺寸，以减少不必要的填充空白。

## Fallback / Edge Cases
- 若计算出的 `k` 值导致最终图片过大（例如超过 4000px），检查是否误用了极小的源图尺寸。此时应重新确认源图是否为缩略图，若是则需寻找原始高分辨率版本。
- 若适配器持续报错但本地校验通过，检查 `images-decisions.json` 的文件编码是否为 UTF-8，且 JSON 格式无 trailing commas。

## Pitfalls
- 步骤 1：切勿直接使用编辑后的图片尺寸作为源尺寸提交，这会导致纵横比校验失败。必须始终回溯到原始上传文件。
- 步骤 3：缩放因子 `k` 必须是整数。使用浮点数缩放会导致最终像素尺寸出现小数截断误差，从而无法通过“exact integer ratio”校验。
