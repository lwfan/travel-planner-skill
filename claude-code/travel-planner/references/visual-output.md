# Visual Output

当用户要求“带图版”“一图流”“长图”“攻略海报”“HTML 页面”“导出图片/PDF”“做成文档”时使用本参考。视觉输出是最终交付层，不替代旅行事实核实和路线设计。

如果用户只是把现有方案换成另一种输出形式，沿用已确认的需求和已核实内容，不重新发旅行问卷或全量搜索路线。只有明显过期、缺失或相互矛盾的信息会影响交付时，才针对该项补查。

## 1. 先判断交付形态

优先级：

1. **HTML-first 视觉行程页**：适合需要美观、可截图、可导出 PNG/PDF 的完整攻略。
2. **文档版**：适合要给同行人转发、打印、补充长解释和预订链接。
3. **一图流**：适合社交分享或手机保存，只放摘要，不放复杂细节。

默认推荐 HTML-first，因为版式、图片比例、信息层级和导出尺寸都更可控。

默认产物：

- 用户选择 `带图 HTML` 或泛称“带图版”：生成 HTML，并额外导出一张完整长图（full-page PNG）；HTML 是源文件，长图方便分享
- 用户选择 `一图流`：生成较短的摘要 HTML 和一张较短的一图流 PNG，保留路线、核心锚点、预算和提醒，不塞完整说明
- 用户选择 `纯文字`：只输出文本行程，不主动搜图或导出图片
- 用户选择 `文档版`：优先生成适合打印/转发的文档结构，可按需插图

## 2. 图片选择规则

图片只服务三个目的：

- 目的地识别：城市天际线、海滩、地标、景区入口
- 行程体验：跳岛、博物馆、徒步、夜景、美食
- 决策辅助：酒店区域、交通枢纽、路线区块

当环境支持图片搜索时，视觉版行程要主动做图片素材检索。推荐最小配图包：

- Hero 图：目的地最具识别度的横图 1 张
- 每日图：每天或每个重点区域 1 张；5 天行程通常至少需要 5 张日程/景点图
- 核心锚点图：凡是日程标题、主活动或用户特别关心的景点，尽量一一配图
- 备选图：天气备选、夜景、美食或亲子体验图 1-2 张

先列“视觉锚点清单”，再搜图。视觉锚点通常包括：

- 每天的主景点或主体验
- 路线中被反复提到的地标、海滩、岛屿、博物馆、徒步线、美食
- 用户在偏好里点名的活动，例如潜水、沙丁鱼风暴、动物保护区、日落

示例：薄荷岛 5 天如果写了 Balicasag、Napaling Sardine Run、Chocolate Hills、Tarsier Sanctuary、Loboc River，就不要只放 Balicasag 和 Chocolate Hills；至少要让沙丁鱼、眼镜猴、Loboc River 也有对应图片，或明确标注未找到可靠图源。

搜索关键词要具体，不要只搜国家或城市名。优先组合：

- `目的地 + 官方旅游局 + 景点名`
- `城市/岛屿 + landmark / beach / museum / old town`
- `景点名 + official photo`
- `景点名 + Wikimedia Commons`

选图顺序：

1. 官方旅游局、景点官网、官方票务、酒店/航司/交通官方图
2. 用户提供或明确授权的图片
3. Wikimedia Commons / Unsplash 等可复用授权图片
4. 普通网页图片只作参考，除非能保留来源并确认使用场景合理

不要使用：

- 与目的地无关的库存感图片
- 过暗、过度裁切、看不清主体的图
- 版权来源不明且无法署名的图片
- 可能误导用户判断实景的生成图，除非明确标注为示意图
- 不对应的替代图，例如用普通海滩代替沙丁鱼风暴、用任意猴子代替菲律宾眼镜猴

每张进入视觉版的图片都要记录：

- 图片 URL 或本地路径
- 来源页面 URL
- 标题 / 景点名
- 作者或来源机构，若可得
- 授权或使用备注，若可得

## 3. 推荐视觉结构

一页视觉行程默认包含：

- 顶部：目的地 / 天数 / 日期 / 推荐基调
- Hero：一张最能代表目的地的横图
- 路线条：城市或区域顺序
- 视觉锚点图集：每天或核心景点的对应美图
- 每日卡片：Day、区域、上午/下午/晚上锚点、1 个备选
- 预算条：大交通、住宿、本地交通、门票体验、餐饮、机动
- 执行清单：现在订、出发前确认、当地决定
- 小字来源：图片来源和硬信息来源链接

详细说明不要塞进一图流。复杂行程应同时给文本版。

完整长图不是固定高度海报。默认做成一张固定宽度、可纵向延展的长图：宽度建议 1080-1440px，高度随内容自然增长。导出时不要用固定 `clip` 截 1080x1920；应使用 full-page screenshot 或先测量页面高度再截图。

一图流可以比完整长图短，但仍然是一张图。建议宽度 1080px，高度控制在适合手机快速浏览的范围；如果核心锚点太多，优先删文字、保留对应图片和标题，不要用错误图片或裁掉底部信息。

## 4. 结构化 JSON

生成 HTML 前，先把行程整理成 JSON。字段可按需省略，但不能只交一个空对象、标题或来源列表；`route`、`days`、`visual_anchors`、`meta`、`budget`、`checklist` 中至少一项需要有实际内容。摘要不必包含完整 `days`。

字段约定：

- `title`、`subtitle`、日程的时间段/交通/用餐/备选等内容使用字符串；`day` 也可使用数字。不要把活动数组直接放进 `morning`，应先整理成一段文本。
- `route`、`checklist`、日程的 `notes` 使用字符串列表。`days`、`visual_anchors` 使用对象列表。为兼容简写，也接受单项字符串或单项对象，类型仍需符合对应条目。
- `meta`、`budget` 使用 `label` / `value` 对象列表，也可使用文本条目；`value` 可为数字。`sources` 使用 `title` / `url` 对象列表，也可使用文本条目。
- 图片可以是路径/URL 字符串，或含 `src`、`caption`、`credit`、`source_url` 的对象；这些图片对象字段使用字符串。`caption`、`credit` 可省略，仅有 `source_url` 时仍会显示“图片来源”链接。
- 没有可靠图片时仍保留视觉锚点的 `name` 和 `description`，并用 `note` 说明原因；省略 `image` 即可，不要删除整个景点。页面会保留文字并显示“未配图”。
- 错误类型和空条目会给出具体字段位置，例如 `days[0].morning`；修正 JSON 后再导出。直接调用 Python 的 `build_html(data)` 时也执行相同的结构与内容校验。

```json
{
  "title": "菲律宾 5 天行程",
  "subtitle": "马尼拉入境 + 长滩岛 3 晚",
  "hero_image": {
    "src": "https://example.com/boracay.jpg",
    "caption": "Boracay White Beach",
    "credit": "Source name",
    "source_url": "https://example.com/source-page"
  },
  "meta": [
    {"label": "天数", "value": "5 天 4 晚"},
    {"label": "节奏", "value": "均衡"}
  ],
  "route": ["马尼拉", "Caticlan", "长滩岛", "马尼拉"],
  "visual_anchors": [
    {
      "day": "Day 2",
      "name": "Balicasag Island",
      "description": "海龟浮潜 / 潜水",
      "image": {
        "src": "https://example.com/balicasag.jpg",
        "credit": "Source",
        "source_url": "https://example.com/source-page"
      }
    }
  ],
  "days": [
    {
      "day": "Day 1",
      "area": "马尼拉 / 长滩岛",
      "image": {
        "src": "https://example.com/day1.jpg",
        "credit": "Source",
        "source_url": "https://example.com/source-page"
      },
      "morning": "抵达马尼拉",
      "afternoon": "转机到 Caticlan，上岛入住",
      "evening": "White Beach 日落",
      "backup": "如果航班延误，只保留入住和晚餐"
    }
  ],
  "budget": [
    {"label": "住宿", "value": "PHP 12,000-24,000"}
  ],
  "checklist": [
    "出发前 72 小时填写 eTravel",
    "优先预订 Caticlan 机场航班"
  ],
  "sources": [
    {"title": "Official tourism page", "url": "https://example.com"}
  ]
}
```

## 5. HTML 生成

使用脚本：

```bash
python3 scripts/visual_plan.py plan.json --output travel-plan.html
```

本地图片的相对路径按 **JSON 文件所在目录** 解析，与运行命令的目录无关。脚本会先校验全部数据并读取本地图片，再生成 HTML；读取失败会报告具体图片字段，不会用断图替代成功交付。输出目录不存在时会自动创建。

例如 `specs/plan.json` 引用 `assets/day.svg`，导出到 `exports/travel-plan.html` 时，脚本读取 `specs/assets/day.svg`，将素材复制到 `exports/travel-plan-assets/`，并使用相对链接引用。转发或移动时，将 HTML 和相邻的 `travel-plan-assets` 文件夹一起打包，保留目录关系。图片按内容生成文件名，相同素材可复用。

HTTP(S)、协议相对 URL 和 `data:` 图片保留原地址，脚本不联网下载；网络图片仍需在截图前确认加载成功。只希望生成 HTML 字符串时使用 `build_html(data)`；需要解析并打包本地素材时使用上面的 CLI，或 Python 的 `write_plan(data, spec_dir, output_path)`（后两个参数为 `Path`）。

如果运行环境支持浏览器或 Playwright，可以再把 HTML 导出为 PNG/PDF。导出前需要检查：

- 图片是否全部加载成功
- 每个核心视觉锚点是否有对应图片；无图时是否明确说明，而不是用错图替代
- 长标题、预算区间、日期是否溢出
- 手机宽度下卡片是否仍然可读
- 来源小字是否保留

一图流 PNG 导出建议：

- 视口宽度固定，例如 1080 或 1200
- 高度使用页面自然高度，或 Playwright `fullPage: true`
- 不要用固定高度 clip 裁切长图，除非用户明确要海报比例

如果无法导出图片，直接交付 HTML 文件路径和文本版行程，并说明未完成图片导出。

## 6. 文档版

用户更需要打印、分享给同行人、保存预订信息时，选择文档版。文档版要保留：

- 完整日程
- 预订链接和确认编号占位
- 每日交通方式
- 风险和备选
- 图片来源和信息来源

## 7. 一图流边界

一图流只适合做最终摘要，不适合承载全部事实依据。最多放：

- 1 张 Hero 图
- 5-9 张每日或核心景点图，数量随天数和核心锚点自然增加
- 每日 2-3 条锚点
- 预算和清单摘要

如果用户要求“所有细节都放一张图”，要提醒可读性会变差，并建议“长图摘要 + 详细文档”组合。
