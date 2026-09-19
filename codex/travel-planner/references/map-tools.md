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
- 即使已经填了 `AK/SK`，只要没有在本地配置中设置 `enabled=true`，百度就不会执行请求
- 设置 `enabled=true` 后也只允许显式使用 `--provider baidu`；`auto` 仍只使用高德

## 2. 推荐命令

### 地点解析

```bash
python3 scripts/map_tools.py geocode --query "故宫博物院" --city 北京
```

### 路线估算

```bash
python3 scripts/map_tools.py route --origin "北京大兴国际机场" --destination "崇文门" --mode subway --city 北京
python3 scripts/map_tools.py route --origin "崇文门" --destination "天坛公园" --mode taxi --city 北京
python3 scripts/map_tools.py route --origin "前门" --destination "天坛公园" --mode bus --city 北京
python3 scripts/map_tools.py route --origin "前门" --destination "大栅栏" --mode walking --city 北京
```

四种常见出行方式及兼容选项：

| `--mode` | 实际含义 | 输出说明 |
| --- | --- | --- |
| `subway` | 从高德返回的公共交通候选中选取第一条包含已确认地铁段的方案 | 通过 `buslines.type=地铁线路` 确认；允许公交、铁路等接驳，不承诺全程地铁。没有此类候选则 `no_route` |
| `taxi` | 使用驾车路线估计车上时间 | `resolved_mode=driving`；不含叫车、候车时间，不提供出租车报价 |
| `walking` | 全程步行 | 不受公共交通的短途步行降级上限影响 |
| `bus` | 高德公共交通 `strategy=5`，不乘地铁 | 可能含步行或铁路等接驳，必须看实际分段；不要把有铁路的方案说成纯公交 |
| `transit` | 地铁、公交、铁路等公共交通混合方案 | 保留原默认值；不能把它直接称为地铁 |
| `driving` | 驾车估时 | 保留原兼容选项 |

`subway` 是对**返回候选**的地铁优先筛选，不代表遍历全部地铁方案。路线的 `details.legs` 保留线路名、类型和上下车站，`details.actual_modes` 列出已识别的实际方式；无法确认的线路类型标为 `unknown`。只有已识别的乘车段全为地铁或全为公交时，`resolved_mode` 才分别是 `subway` 或 `bus`；混合或存在未确认方式时为 `transit`。`mode` 始终保留用户请求的方式。

这些策略和字段依据[高德 V3 路径规划官方文档](https://lbs.amap.com/api/webservice/guide/api/direction)。百度适配器尚未实现 `subway`、`bus`，显式请求会返回 `unsupported`，不会用混合公共交通冒充。

### 同一路段比较多种交通

```bash
python3 scripts/map_tools.py compare-modes --origin "崇文门" --destination "天坛公园" --city 北京
python3 scripts/map_tools.py compare-modes --origin "崇文门" --destination "天坛公园" --city 北京 --modes subway taxi bus --preference least-walking --max-total-walk-km 1.2
```

默认比较地铁、打车、步行、公交，`--modes` 可缩小到用户允许的方式，重复方式只查询一次。支持 `--city` 或分别指定 `--origin-city` / `--destination-city`，所有候选使用相同起终点。

`options` 保留请求顺序，每项包含查询状态、实际交通组成、标准化 `metrics`、约束判断、说明和原始路线结果；失败的方式也会保留，不中断其他方案。

| 指标 | 口径 |
| --- | --- |
| `duration_minutes` | 地图返回的路线估时；打车为驾车估时，不含候车，不能直接当作完整门到门时间 |
| `fare_cny` | 已知交通票价；纯步行为 0，打车/驾车车费未知时为 `null`，不能用过路费替代车费 |
| `walking_distance_m` | 已知接驳步行量；纯步行为全程距离；打车上下车接驳未知时为 `null` |
| `transfers` | 已知乘车段之间的换乘次数，步行不计；分段信息不足时为 `null`，不从总段数猜测 |

`--preference` 只决定一个有明确依据的建议：

- `fastest`（默认）：已知地图估时较短；候车等时间缺项仍需补核。
- `cheapest`：**已知票价的候选中**较省，不代表缺报价的其他方式更贵。按人/按车、人数、购票条件等仍需在用户输出中统一口径。
- `least-walking`：已知步行距离较少；未知接驳量不能当作 0。
- `fewest-transfers`：已知换乘次数较少；换乘少不自动代表最省时间或无障碍可用。

所有方案仍会展示，`recommendation` 是建议而不是用户的选择；没有足够依据或没有满足约束的方案时为 `null` 并说明原因。用户之后可选择另一种方式。

可选 `--max-total-walk-km` 是**整段路线的步行上限**，包括公共交通接驳；超过上限的候选保留但不推荐，步行量未知的标为待核实。它与单路线 `route` 的步行替代阈值不同，也不验证全天总步行量；用户限制单日步行时，规划层需累计各路段和景点内步行后分配剩余额度。

比较时公共交通的自动步行替代始终关闭，避免地铁、公交和步行三行实际都是步行。无路线的方式显示无路线；不会因为某方式失败就改成另一方式冒充。关键路段按需展示 2-3 个有取舍的可行选择，用户要全量时再列全部，不必对每一段都查询四种方式。

### 同城与跨城

`--city` 是两端共用的城市提示。跨城时分别传 `--origin-city` 与 `--destination-city`，它们会覆盖各自一端的 `--city`，同时用于地点解析和路线请求。例如：

```bash
python3 scripts/map_tools.py route --origin "北京南站" --destination "天津站" --mode transit --origin-city 北京 --destination-city 天津
```

高德公共交通请求会传入必填的 `city`，以及终点 `cityd`。未给城市提示时，脚本尝试从地点解析结果的 `citycode` / `city` 推导；无法确定时返回 `invalid_input`，不要用区县 `adcode` 代替城市编码。

### 区域对比

```bash
python3 scripts/map_tools.py compare-areas --areas 崇文门 前门 东直门 --anchors 故宫博物院 天坛公园 什刹海 --mode subway --city 北京
```

比较住宿区域时应为所有区域选择同一种请求方式；需要比较不同方式下的住宿区域排名时，分别运行 `compare-areas`。同一路段的交通方式选择则使用 `compare-modes`。只有所有锚点均取得有效路线的区域进入 `ranked_areas`；缺失路线的区域进入 `incomplete_areas`，保留每个成功结果、失败原因、`valid_routes`、`total_routes` 与 `coverage`（0–1）。不完整区域的 `average_duration_minutes` 为 `null`，不会把未知耗时当 0，也不会因只查到一个近点而排在完整区域之前。

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
- `status`：`ok` / `no_route` / `unsupported` / `error`；区域比较还可能是 `partial`
- `mode` / `resolved_mode`：用户请求的方式 / 路线实际采用的方式；两者不同必须说明
- `duration_minutes`：更适合拿来判断节奏，而不是当成绝对承诺
- `distance_km`：适合判断区域远近和打车价值
- `average_duration_minutes`：有完整覆盖时的平均耗时，仍只是粗粒度指标；缺失时为 `null`

只有公共交通接口**成功返回空路线列表**，才允许尝试短途步行替代；认证失败、限流、网络异常和格式错误都不会变成步行方案。默认替代步行必须同时不超过 **1.5 km 与 25 分钟**。过长或步行也无路线则返回 `no_route`。

上限可以按同行者情况调整，适用于 `subway`、`bus`、`transit` 的空公共交通结果；任一上限设为 0 可关闭步行替代：

```bash
python3 scripts/map_tools.py route --origin "前门" --destination "大栅栏" --mode subway --city 北京 --max-walk-km 0.8 --max-walk-minutes 15
python3 scripts/map_tools.py compare-areas --areas 崇文门 东直门 --anchors 故宫博物院 天坛公园 --mode subway --city 北京 --max-walk-km 0
```

替代结果会明确带 `resolved_mode=walking`、`details.fallback_from` 和 `details.fallback_reason`。如果用户要求必须地铁或公交，关闭替代；不要把步行替代说成满足了原交通限制。公共交通存在候选、但没有已确认地铁段时，`subway` 直接返回 `no_route`，不会再尝试步行。

## 5. 使用边界

这套工具主要解决“空间与路线”问题，不直接解决：

- 景点开放时间
- 门票价格
- 签证/入境规则
- 活动和展览是否还在售

这些仍然需要搭配官网、政府页、票务页和普通 web 搜索核实。

## 6. 失败时怎么处理

如果统一入口返回异常：

- 先看 JSON 中 `error.code`：`no_route` 是无可用路线，`invalid_response` 是响应不完整，`api_error` / `network_error` 是服务或网络失败，`unsupported` 是适配器未实现该方式
- 地点问题换标准名称，并加 `--city` 或分别指定两端城市
- 配置问题检查相应后端；百度仍需检查是否确实需要启用，以及 `enabled`、`AK`、`SK`
- 区域比较出现 `partial` 时，先使用保留的有效结果，补核失败项后再做整体排名
- 无法修复时，用 web 搜索或地图网页手动确认，并保留“未核实”标记

正常完成时退出码为 0；无路线、错误或比较结果不完整时退出码为 1，但仍输出可解析 JSON。调用方应读取结果，不要因非零退出码直接丢弃已有区域对比数据。
