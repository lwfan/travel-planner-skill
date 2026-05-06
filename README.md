# Travel Planner Skill

一个用于旅行规划的 AI skill，支持把模糊出游想法拆成可执行的旅行简报、路线策略、按天行程、预算和预订清单。

仓库同时提供两个版本：

- `codex/travel-planner/`：Codex 版本，包含 `agents/openai.yaml` UI 元数据。
- `claude-code/travel-planner/`：Claude Code 版本，保留相同的 `SKILL.md`、`scripts/` 和 `references/`。

## 功能

- 首轮先收集旅行简报，避免信息不足时直接硬排行程
- 默认核实签证、入境、天气、开放时间、票价、交通时刻等易变信息
- 支持城市区域对比、点到点路线估算和景点地理聚类
- 输出按天行程、预算范围、预订清单、风险提示和备选方案
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
