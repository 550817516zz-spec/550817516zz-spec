---
name: image-prompt
description: 把用户的画面想法转换为可用于即梦、Midjourney、Stable Diffusion 等工具的高质量绘图提示词。
---

# Image Prompt Writer

## 用途

当用户想“生成图片”、描述一个画面、需要配图，或要求绘图提示词时使用本技能。

本技能不直接生成图片，而是产出可以直接粘贴到绘图工具中的提示词。若当前环境已经接入图片生成工具，则先整理提示词，再调用对应工具。

## 工作流程

1. 从用户描述中提取以下要素：
   - 主体：人物、动物、产品、建筑、风景或抽象概念
   - 动作/状态：正在做什么，画面里发生了什么
   - 环境：地点、时间、天气、背景
   - 风格：写实、电影感、动漫、国风、赛博朋克、3D、水彩等
   - 构图：特写、半身、全身、俯视、广角、中心构图、留白
   - 光线：自然光、逆光、霓虹、体积光、柔光、硬光
   - 色彩：冷暖、单色、高饱和、低饱和、主色调
   - 画幅：1:1、16:9、9:16、4:3
2. 信息足够时直接输出，不要反复追问。
3. 只缺少关键信息时，最多追问 1–2 个问题。
4. 用户没有指定风格时，默认选择与主题最匹配的风格，并说明选择原因。
5. 需要具体风格模板时，调用：
   `loadSkill(name="image-prompt", filename="references/style-presets.md")`

## 输出格式

每次输出以下内容：

```text
【中文提示词】
...

【English Prompt】
...

【Negative Prompt】
...

【推荐参数】
画幅：...
风格：...
其他：...
```

如果用户明确使用 Midjourney，英文提示词末尾可附参数，例如：
`--ar 16:9 --style raw --v 6`

如果用户使用 Stable Diffusion，补充推荐：
- 采样器
- 步数
- CFG Scale
- 负面提示词

## 写作要求

- 提示词必须具体、可视、可执行，避免“好看”“高级”“有感觉”这类空泛词。
- 优先描述画面中能看到的东西：主体、动作、材质、环境、光线、镜头。
- 人物描述要包含外貌、服装、姿态、表情和镜头距离。
- 场景描述要包含前景、中景、背景和空间关系。
- 不要堆砌互相冲突的风格。
- 用户要求多种方案时，给出 2–3 个差异明显的变体，而不是只换几个形容词。
- 不声称已经生成图片；没有图片工具时，只提供提示词。

## 示例

用户输入：

```text
一个女孩站在雨夜街头，赛博朋克风格，适合做手机壁纸
```

输出要点：

```text
【中文提示词】
一位年轻女孩站在雨夜霓虹街头，黑色短发被雨水打湿，身穿半透明机能风外套，侧身回望镜头，背景是密集的日文招牌与紫蓝色霓虹灯，地面积水反射灯光，电影感构图，浅景深，冷色调，高对比度，竖屏手机壁纸。

【English Prompt】
A young woman standing on a rain-soaked neon-lit street at night, short wet black hair, translucent techwear jacket, looking back over her shoulder, dense Japanese signage and purple-blue neon reflections, puddles mirroring the lights, cinematic composition, shallow depth of field, cool color palette, high contrast, vertical mobile wallpaper, ultra detailed, 9:16.

【Negative Prompt】
low quality, blurry, deformed hands, extra fingers, bad anatomy, watermark, text, oversaturated, flat lighting

【推荐参数】
画幅：9:16
风格：赛博朋克 / 电影摄影
其他：浅景深，高对比，霓虹反射
```
