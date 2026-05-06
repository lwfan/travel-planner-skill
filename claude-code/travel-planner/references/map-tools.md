# Map Tools

`travel-planner` 现在使用统一地图入口 `scripts/map_tools.py`：

- 高德作为主提供方
- 百度实现已保留，但当前默认禁用，视作注释/预留状态

## 1. 配置来源

高德配置：

- `amap-config.local.json`
- 或环境变量 `AMAP_API_KEY`

百度配置：

- `baidu-config.local.json`
- 或环境变量 `BAIDU_MAP_AK` / `BAIDU_MAP_SK`

注意：

- 百度当前按 `sn` 校验方式设计
- 默认不启用百度后端
- 即使已经填了 `AK/SK`，只要没有在本地配置中设置 `enabled=true`，百度就不会参与自动 fallback
- 只有后续显式配置 `enabled=true` 时，才恢复百度后端

## 2. 推荐命令

### 地点解析

```bash
python3 scripts/map_tools.py geocode --query "故宫博物院" --city 北京
```

### 路线估算

```bash
python3 scripts/map_tools.py route --origin "北京大兴国际机场" --destination "崇文门" --mode transit --city 北京
```

### 区域对比

```bash
python3 scripts/map_tools.py compare-areas --areas 崇文门 前门 东直门 --anchors 故宫博物院 天坛公园 什刹海 --mode transit --city 北京
```

## 3. provider 选择

默认值：

- `--provider auto`

可选值：

- `auto`
- `amap`
- `baidu`

示例：

```bash
python3 scripts/map_tools.py geocode --query "天坛公园" --city 北京 --provider amap
python3 scripts/map_tools.py geocode --query "天坛公园" --city 北京 --provider baidu
```

在 `auto` 模式下：

- 只尝试高德

如果未来要恢复百度：

1. 新建 `baidu-config.local.json` 并设置 `enabled=true`
2. 再单独测试 `--provider baidu`
3. 确认百度平台侧服务已真正可用后，再考虑恢复自动 fallback

## 4. 结果如何解读

- `provider_used`：本次实际成功使用的地图提供方
- `resolved_mode`：路线规划最终采用的模式
- `duration_minutes`：更适合拿来判断节奏，而不是当成绝对承诺
- `distance_km`：适合判断区域远近和打车价值
- `average_duration_minutes`：区域对比时的粗粒度指标，越低通常越顺

如果 `transit` 对非常近的两点不给公交方案，脚本会自动回退到 `walking`。

## 5. 使用边界

这套工具主要解决“空间与路线”问题，不直接解决：

- 景点开放时间
- 门票价格
- 签证/入境规则
- 活动和展览是否还在售

这些仍然需要搭配官网、政府页、票务页和普通 web 搜索核实。

## 6. 失败时怎么处理

如果统一入口返回异常：

- 先检查地点写法是否过于口语化
- 换成更标准的地点名称
- 加上 `--city`
- 如果是百度，先确认是否真的需要恢复，并检查 `enabled`、`AK`、`SK`
- 如果仍然失败，再用 web 搜索或地图网页手动确认
