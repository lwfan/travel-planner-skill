# Travel Planner Skill

一个用于旅行规划的 AI skill，支持把模糊出游想法拆成可执行的旅行简报、路线策略、按天行程、预算和预订清单。

仓库同时提供两个版本：

- `codex/travel-planner/`：Codex 版本，包含 `agents/openai.yaml` UI 元数据。
- `claude-code/travel-planner/`：Claude Code 版本，保留相同的 `SKILL.md`、`scripts/` 和 `references/`。

## 功能

- 新建行程先补齐关键偏好；已确认条件或授权默认后直接继续，局部调整与格式转换不重复问卷
- 默认核实签证、入境、天气、开放时间、票价、交通时刻等易变信息
- 支持城市区域对比、点到点路线估算和景点地理聚类，按地铁、打车、步行、公交偏好选择出行方式
- 支持同一路段多交通方案对比，展示耗时、已知票价、步行与换乘；整趟行程也可提供有实际取舍的候选版本供用户选择
- 输出按天行程、预算范围、预订清单、风险提示和备选方案
- 文件产物按单次行程集中保存；通用工作目录下归入 `旅行计划/`，旅游总目录下直接分行程，后续修改和导出复用原目录
- 可选视觉交付：搜索插图素材，生成带图 HTML 行程页，再按环境导出图片或 PDF

## 安装到 Codex

```bash
mkdir -p ~/.codex/skills
cp -R codex/travel-planner ~/.codex/skills/travel-planner
```

## 安装到 Claude Code

```bash
mkdir -p ~/.claude/skills
cp -R claude-code/travel-planner ~/.claude/skills/travel-planner
```

## 地图工具配置

地图工具优先使用高德地图 API。可以用环境变量配置：

```bash
export AMAP_API_KEY="your-amap-api-key"
```

也可以在 skill 目录下新建本地配置文件：

```json
{
  "api_key": "your-amap-api-key"
}
```

文件名使用 `amap-config.local.json`。本仓库已通过 `.gitignore` 排除本地配置文件，避免误传密钥。

## 行程文件保存位置

用户明确指定的输出路径优先。未指定时：

| 当前工作环境 | 文件保存位置 |
| --- | --- |
| 通用工作目录 | `旅行计划/<单次行程>/` |
| 专属旅游总目录 | `<单次行程>/` |
| 已有单次行程或其子目录 | 复用原行程目录 |

JSON、Markdown、HTML、PNG、PDF、图片素材和本次生成的渲染辅助脚本集中在同一行程目录内；候选方案使用不同文件名，不重复嵌套目录。纯聊天或单项查询不创建目录。

在 skill 目录下调用目录工具：

```bash
python3 scripts/output_paths.py --workspace "/path/to/workspace" --trip-name "北京3天"
python3 scripts/output_paths.py --workspace "/path/to/workspace" --trip-name "北京3天" --create
```

默认只返回目录解析 JSON；`--create` 才创建目录和标记。自动识别使用精确集合名、有效 `.travel-planner.json` 标记和有边界的祖先查找，不依赖宽泛的 `travel` 子串。用户明确说明非标准名称的工作目录是旅游总目录时，使用 `--workspace-type travel`；不确定时按通用目录处理。

`visual_plan.py` 默认将 HTML 输出到行程目录内的 `travel-plan.html`，支持 `--workspace`、`--workspace-type` 和 `--trip-name`。显式 `--output` 保留指定路径优先的行为。完整规则见 [输出目录说明](codex/travel-planner/references/output-directory.md) 和 [视觉交付说明](codex/travel-planner/references/visual-output.md)。

## 目录结构

```text
.
├── codex/
│   └── travel-planner/
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       ├── references/
│       └── scripts/
└── claude-code/
    └── travel-planner/
        ├── SKILL.md
        ├── references/
        └── scripts/
```

## 更新方式

Codex 和 Claude Code 两个版本目前内容保持一致，区别只是 Codex 版本额外包含 `agents/openai.yaml`。更新时建议先改 `codex/travel-planner/`，再同步到 `claude-code/travel-planner/`，同步时不要复制 `agents/`。

## 验证修改

在仓库根目录运行离线回归测试：

```bash
python3 -B -m unittest discover -s tests -v
```

测试使用模拟地图响应和临时本地图片，不需要地图密钥或访问真实地图 API。地图参数、交通方式和失败结果的含义见各版本的 `references/map-tools.md`；视觉 JSON 与本地素材交付规则见 `references/visual-output.md`。
