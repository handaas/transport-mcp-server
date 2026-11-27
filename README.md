# 交通大数据

[该 MCP 服务提供沿海散货和出口集装箱运价指数查询，以及公路水路、铁路、民航、邮政、城市客运、港口和交通运输投资统计明细查询能力，用于交通运输运行监测与辅助研判。](https://www.handaas.com/)

## 主要功能

- 🚢 沿海（散货）运价指数与分品类环比增长查询
- 📦 出口集装箱运价指数及 12 条主要航线指数查询
- 🚚 公路水路客货运输量与周转量统计（支持全国/分省）
- 🚆 铁路客货发送量、周转量与固定资产投资统计
- ✈️ 民航客货邮运输量、总周转量及客座率统计（按国内/港澳台/国际航线拆分）
- 📮 邮政行业收入、快递量结构与普遍服务业务量统计
- 🚌 城市客运总量及公交、出租、轨道交通、轮渡客运量统计（支持全国/分省）
- ⚓ 港口货物、外贸货物与集装箱吞吐量统计（支持全国/分省）
- 🏗️ 公路水路、公路、水运、内河及沿海建设投资统计（支持全国/分省）

## 工具速览

| Tool | 用途 | 关键参数 | `statTime` |
| --- | --- | --- | --- |
| `transport_coastal_bulk_freight_index` | 查询沿海散货综合及分品类运价指数 | `statTime` | 必填（`YYYY-MM`） |
| `transport_export_container_freight_index` | 查询出口集装箱综合及各航线运价指数 | `statTime` | 必填（`YYYY-MM`） |
| `transport_highway_waterway_statistics` | 查询公路水路客货运输量与周转量 | `statTime`、`regionType` | 必填（`YYYY-MM`） |
| `transport_railway_statistics` | 查询铁路客货运输量、周转量与投资 | `statTime` | 必填（`YYYY-MM`） |
| `transport_civil_aviation_statistics` | 查询民航客货邮运输量、周转量与客座率 | `statTime` | 必填（`YYYY-MM`） |
| `transport_postal_statistics` | 查询邮政收入、快递量结构与普遍服务 | `statTime` | 必填（`YYYY-MM`） |
| `transport_urban_passenger_statistics` | 查询城市客运总量及分方式客运量 | `statTime`、`regionType` | 必填（`YYYY-MM`） |
| `transport_port_statistics` | 查询港口货物、外贸货物与集装箱吞吐量 | `statTime`、`regionType` | 必填（`YYYY-MM`） |
| `transport_investment_statistics` | 查询公路水路固定资产建设投资 | `statTime`、`regionType` | 必填（`YYYY-MM`） |

`statTime` 对全部 9 个工具均为必填项，仅接受单月格式 `YYYY-MM`（如 `2025-01`）；若 1 月数据为空，可尝试查询 2 月（存在 1、2 月数据合并发布到 2 月的情况）。`regionType` 为可选参数，仅接受 `country`（全国）或 `province`（省份）。

## 环境要求

- Python 3.10+
- 依赖包：`python-dotenv`、`requests`、`mcp`

## 本地快速启动

### 1. 克隆项目

GitHub（公开仓库）：

```bash
git clone https://github.com/handaas/transport-mcp-server.git
cd transport-mcp-server
```

Gitee（公开镜像）：

```bash
git clone https://gitee.com/handaas/transport-mcp-server.git
cd transport-mcp-server
```

以上地址是源码仓库，不是可直接连接的托管 MCP 服务地址。

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv mcp_env
source mcp_env/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```env
INTEGRATOR_ID=your_integrator_id
SECRET_ID=your_secret_id
SECRET_KEY=your_secret_key
HANDAAS_REQUEST_TIMEOUT=30
FASTMCP_PORT=8001
```

- `INTEGRATOR_ID`、`SECRET_ID`、`SECRET_KEY`：HandaaS 对接器认证信息。
- `HANDAAS_REQUEST_TIMEOUT`：可选，上游请求超时秒数，默认 30。
- `FASTMCP_PORT`：可选，本地 HTTP 监听端口，默认 8000；示例使用 8001，以减少与其他 MCP 服务的端口冲突。

认证信息需要登录 [HandaaS](https://www.handaas.com/) 注册并开通对应数据产品后获取。不要提交 `.env`、真实凭据或真实业务响应。

服务启动时只自动读取本服务目录下的 `.env`。同名进程环境变量优先于 `.env`：适合在 CI 或 MCP 客户端中直接注入凭据。`python server/mcp_server.py ...` 可只使用进程环境变量，不强制要求 `.env` 文件；`start_mcp_server.sh` 则会先检查本目录的 `mcp_env/` 和 `.env`，缺少任一项都会退出。

### 4. 启动服务

服务支持 `stdio`、`sse` 和 `streamable-http` 三种传输方式：

```bash
# STDIO
python server/mcp_server.py stdio

# Streamable HTTP
python server/mcp_server.py streamable-http

# SSE
python server/mcp_server.py sse
```

也可以使用启动脚本；省略参数时默认启动 `streamable-http`：

```bash
./start_mcp_server.sh
./start_mcp_server.sh stdio
./start_mcp_server.sh sse
```

使用示例端口 `8001` 时，Streamable HTTP MCP 地址为 `http://127.0.0.1:8001/mcp`。

- 直接运行 Python 且省略传输参数时，默认使用 `stdio`。
- 启动脚本省略传输参数时，默认使用 `streamable-http`。
- `sse` 和 `streamable-http` 固定监听 `127.0.0.1`；端口取 `FASTMCP_PORT`，未配置时为 `8000`。修改端口后应同步修改客户端 URL。

## Cursor / Cherry Studio 配置

### Streamable HTTP

先在项目目录启动 `python server/mcp_server.py streamable-http`，再添加：

```json
{
  "mcpServers": {
    "transport-mcp-server": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

### STDIO

将 `{workdir}` 替换为 `transport-mcp-server` 的绝对路径：

```json
{
  "mcpServers": {
    "transport-mcp-server": {
      "command": "{workdir}/mcp_env/bin/python",
      "args": ["{workdir}/server/mcp_server.py", "stdio"],
      "env": {
        "INTEGRATOR_ID": "your_integrator_id",
        "SECRET_ID": "your_secret_id",
        "SECRET_KEY": "your_secret_key",
        "HANDAAS_REQUEST_TIMEOUT": "30"
      }
    }
  }
}
```

## 使用官方 Remote 服务

当前服务尚未发布官方 Remote 地址。请使用本地 `stdio`、`sse` 或 `streamable-http` 方式运行；官方 Remote 地址发布后再补充远程配置。

## 推荐调用方式

1. 调用任意 Tool 时，均必须传入单月格式 `statTime`（如 `2025-01`、`2026-04`）；若统计类接口在 `YYYY-01` 返回空结果（`total=0`），可尝试查询 `YYYY-02`（部分统计期将 1、2 月数据合并到 2 月公布）。
2. 查询公路水路、城市客运、港口、交通投资数据时，先确认需要全国汇总还是分省明细，通过 `regionType="country"` 或 `regionType="province"` 筛选。
3. 多方式综合研判时，分别调用对应运输方式 Tool，并留意各指标自带的 `unit`（单位）和 `statPeriod`（如“月度”或“月累计”），避免把当期值与累计值混为一谈。

## 响应约定

九个 Tool 成功时统一返回 `total/resultList`。以下内容是**合成结构示例**，不包含真实业务数据：

```json
{
  "total": 1,
  "resultList": [
    {
      "year": 2025,
      "statTime": "5月",
      "statPeriod": "月度",
      "coastalBulkFreightIndex": {
        "lastYear": 1000.0,
        "currentYear": 1012.5,
        "currentMonth": 1020.3,
        "momGrowth": -1.2
      },
      "extraUpstreamField": "客户端应兼容的上游扩展字段"
    }
  ]
}
```

MCP 会保留 `resultList` 每条记录中的上游未知字段，不会为了匹配本文档而删除扩展字段；同时兼容上游 `dataList`、`resultList`、领域明细列表（如 `hwWayList`、`railwayList` 等）与单对象响应。`total=0` 且 `resultList=[]` 只表示当前筛选没有返回记录，不能解释为无运输活动或运价未变化。

参数校验、网关或上游错误返回包含 `error` 的对象，并可能附带 `parameter`、`code`、`statusCode` 或 `diagnostic`。例如，无效统计时间的合成错误结构为：

```json
{
  "error": "统计时间格式不合法，仅支持单月格式 YYYY-MM，如 2025-01",
  "parameter": "statTime",
  "code": "INVALID_STAT_TIME"
}
```

通过 MCP 调用时，参数正则、枚举等 Schema 校验也可能在工具执行前直接返回 `isError=true`。客户端应同时处理 MCP 协议错误和 `structuredContent` 中的业务 `error`，不能只检查 HTTP 状态码。

## 可用工具

### 1. transport_coastal_bulk_freight_index

**功能**：查询沿海（散货）运价指数及分品类环比增长。

**数据产品 ID**：`6a704e0d61c110074d34228f`

**参数**：

- `statTime`（必填）：统计时间，严格使用单月格式 `YYYY-MM`（如 `2025-01`）。若 1 月数据为空可尝试查询 2 月。

**返回值**：

- `total`：运价指数记录数。
- `resultList`：运价指数列表，每条包含：
  - `year`：统计年份（整数）。
  - `statTime`：统计月份（如 `"5月"`）。
  - `statPeriod`：统计周期（可选/上游部分时期省略）。
  - `coastalBulkFreightIndex`：沿海散货综合指数，含 `lastYear`（去年同期值）、`currentYear`（当年累计均值）、`currentMonth`（当月值）、`momGrowth`（环比增长）。
  - `coalFreightIndex`：煤炭运价指数，子字段同上。
  - `metalOreFreightIndex`：金属矿石运价指数，子字段同上。
  - `grainFreightIndex`：粮食运价指数，子字段同上。
  - `refinedOilFreightIndex`：成品油运价指数，子字段同上。
  - `crudeOilFreightIndex`：原油运价指数，子字段同上。

### 2. transport_export_container_freight_index

**功能**：查询出口集装箱综合运价指数及 12 条主要国际航线运价指数。

**数据产品 ID**：`6a705029c125d8e5a37c2956`

**参数**：

- `statTime`（必填）：统计时间，严格使用单月格式 `YYYY-MM`（如 `2025-01`）。若 1 月数据为空可尝试查询 2 月。

**返回值**：

- `total`：运价指数记录数。
- `resultList`：运价指数列表，每条包含：
  - `year`、`statTime`：统计年份和月份；`statPeriod`（可选/上游部分时期省略）。
  - `exportContainerCompositeIndex`：出口集装箱综合指数，含 `lastYear`、`currentYear`、`currentMonth`、`momGrowth`。
  - `europeRouteIndex`（欧洲航线）、`mediterraneanRouteIndex`（地中海航线）、`westAmericaRouteIndex`（美西航线）、`eastAmericaRouteIndex`（美东航线）、`persianGulfRedSeaRouteIndex`（波红航线）、`australiaNewZealandRouteIndex`（澳新航线）、`westAfricaRouteIndex`（西非航线）、`southAfricaRouteIndex`（南非航线）、`southAmericaRouteIndex`（南美航线）、`japanRouteIndex`（日本航线）、`southeastAsiaRouteIndex`（东南亚航线）、`koreaRouteIndex`（韩国航线），子字段同上。

### 3. transport_highway_waterway_statistics

**功能**：查询公路、水路客货运输量与周转量统计明细，支持全国与省份维度。

**数据产品 ID**：`6a705750c125d8e5a37c2993`

**参数**：

- `statTime`（必填）：统计时间，严格使用单月格式 `YYYY-MM`（如 `2025-01`）。若 1 月数据为空可尝试查询 2 月。
- `regionType`（可选）：地区类型，仅支持 `country`（全国）或 `province`（省份）。

**返回值**：

- `total`：统计明细总数。
- `resultList`：明细列表，每条包含：
  - `region`、`regionType`：地区名称与地区类型（`country` / `province`）。
  - `year`、`statTime`、`statPeriod`：统计年份、月份（如 `"5月"`、`"1-2月"`）与周期（如 `"月度"`、`"月累计"`）。
  - `roadFreightVolume`（公路货物运输量）、`roadPassengerVolume`（公路旅客运输量）、`waterFreightVolume`（水路货物运输量）、`waterPassengerVolume`（水路旅客运输量），以及按上游披露情况返回的 `roadPassengerTurnover`（公路旅客周转量）、`roadFreightTurnover`（公路货物周转量）、`waterPassengerTurnover`（水路旅客周转量）、`waterFreightTurnover`（水路货物周转量）；各指标包含 `currentValue`（当期值）、`cumulativeValue`（累计值）、`yoyGrowth`（同比增长）、`unit`（单位）。

### 4. transport_railway_statistics

**功能**：查询铁路客货发送量、周转量及铁路固定资产投资统计明细。

**数据产品 ID**：`6a705b6961c110074d34242f`

**参数**：

- `statTime`（必填）：统计时间，严格使用单月格式 `YYYY-MM`（如 `2025-01`）。

**返回值**：

- `total`：统计明细总数。
- `resultList`：明细列表，每条包含：
  - `year`、`statTime`、`statPeriod`：统计年份、月份和周期。
  - `passengerDispatchVolume`（旅客发送量）、`passengerTurnover`（旅客周转量）、`freightDispatchVolumeTotal`（货运总发送量）、`freightDispatchVolume`（货物发送量）、`freightTurnoverTotal`（货运总周转量）、`freightTurnover`（货物周转量）、`railwayFixedAssetInvestment`（铁路固定资产投资），各指标均包含 `currentValue`（当期值）、`cumulativeValue`（累计值）、`currentYoyGrowth`（当期同比增长）、`cumulativeYoyGrowth`（累计同比增长）、`unit`（单位）。

### 5. transport_civil_aviation_statistics

**功能**：查询民航旅客运输量、运输总周转量、货邮运输量及客座率统计明细。

**数据产品 ID**：`6a705c7261c110074d3424a2`

**参数**：

- `statTime`（必填）：统计时间，严格使用单月格式 `YYYY-MM`（如 `2025-01`）。

**返回值**：

- `total`：统计明细总数。
- `resultList`：明细列表，每条包含：
  - `year`、`statTime`、`statPeriod`：统计年份、月份和周期。
  - `passengerVolume`（旅客运输量）、`transportTurnover`（运输总周转量）、`cargoMailVolume`（货邮运输量）：均按 `total`（总计）、`domesticRoute`（国内航线）、`hkMacaoTaiwanRoute`（港澳台航线）、`internationalRoute`（国际航线）拆分。
  - `flightEfficiency`：飞行效率，含 `seatLoadFactor`（客座率）。

### 6. transport_postal_statistics

**功能**：查询邮政行业业务收入、快递业务量与收入及邮政普遍服务业务量统计明细。

**数据产品 ID**：`6a705ee4c125d8e5a37c2a70`

**参数**：

- `statTime`（必填）：统计时间，严格使用单月格式 `YYYY-MM`（如 `2025-01`）。

**返回值**：

- `total`：统计明细总数。
- `resultList`：明细列表，每条包含：
  - `year`、`statTime`、`statPeriod`：统计年份、月份和周期。
  - `postalIndustryBusinessIncome`（邮政行业业务收入）、`expressBusinessIncome`（快递业务收入）、`universalPostalServiceBusinessIncome`（邮政普遍服务业务收入）、`postalDeliveryVolume`（邮政行业寄递业务量）、`expressBusinessVolume`（快递业务量）、`intraCityExpressVolume`（同城快递量）、`interCityExpressVolume`（异地快递量）、`internationalHkmtExpressVolume`（国际/港澳台快递量）、`postalGeneralServiceVolume`（邮政普遍服务寄递业务量），以及按统计期披露返回的 `letterMailVolume`（函件量）、`parcelVolume`（包裹量）、`newspaperSubYtdVolume`（订销报纸累计数）、`magazineSubYtdVolume`（订销杂志累计数）、`postalRemittanceVolume`（汇兑量），各指标包含 `currentValue`、`cumulativeValue`、`currentYoy`、`cumulativeYoy`、`unit`。

### 7. transport_urban_passenger_statistics

**功能**：查询城市客运总量及公共汽电车、出租汽车、城市轨道交通、轮渡客运量，支持全国与省份维度。

**数据产品 ID**：`6a70603cc125d8e5a37c2a93`

**参数**：

- `statTime`（必填）：统计时间，严格使用单月格式 `YYYY-MM`（如 `2025-01`）。
- `regionType`（可选）：地区类型，仅支持 `country`（全国）或 `province`（省份）。

**返回值**：

- `total`：统计明细总数。
- `resultList`：明细列表，每条包含：
  - `region`、`regionType`：地区与地区类型（`country` / `province`）。
  - `year`、`statTime`、`statPeriod`：统计年份、月份和周期。
  - `urbanTransportVolume`（城市客运总量）、`busTransportVolume`（公共汽电车客运量）、`taxiTransportVolume`（出租汽车客运量）、`urbanRailTransitVolume`（城市轨道交通客运量）、`urbanFerryVolume`（轮渡客运量），各指标包含 `currentValue`、`cumulativeValue`、`currentYoy`、`cumulativeYoy`、`unit`。

### 8. transport_port_statistics

**功能**：查询港口货物吞吐量、外贸货物吞吐量及集装箱吞吐量，支持全国与省份维度。

**数据产品 ID**：`6a706148c125d8e5a37c2b18`

**参数**：

- `statTime`（必填）：统计时间，严格使用单月格式 `YYYY-MM`（如 `2025-01`）。
- `regionType`（可选）：地区类型，仅支持 `country`（全国）或 `province`（省份）。

**返回值**：

- `total`：统计明细总数。
- `resultList`：明细列表，每条包含：
  - `region`、`regionType`：地区与地区类型（`country` / `province`）。
  - `year`、`statTime`、`statPeriod`：统计年份、月份和周期。
  - `cargoThroughput`（货物吞吐量）、`foreignTradeCargoThroughput`（外贸货物吞吐量）、`containerThroughput`（集装箱吞吐量），各指标包含 `currentValue`、`cumulativeValue`、`cumulativeYoy`、`unit`。

### 9. transport_investment_statistics

**功能**：查询交通运输建设投资统计明细，支持全国与省份维度。

**数据产品 ID**：`6a70617f61c110074d342595`

**参数**：

- `statTime`（必填）：统计时间，严格使用单月格式 `YYYY-MM`（如 `2025-01`）。
- `regionType`（可选）：地区类型，仅支持 `country`（全国）或 `province`（省份）。

**返回值**：

- `total`：统计明细总数。
- `resultList`：明细列表，每条包含：
  - `region`、`regionType`：地区与地区类型（`country` / `province`）。
  - `year`、`statTime`、`statPeriod`：统计年份、月份和周期。
  - `highwayWaterwayConstructionInvestment`（公路水路建设投资）、`highwayConstructionInvestment`（公路建设投资），以及按地区与上游披露情况返回的 `waterwayConstructionInvestment`（水运建设投资）、`inlandWaterwayConstructionInvestment`（内河建设投资）、`coastalWaterwayConstructionInvestment`（沿海建设投资），各指标包含 `currentValue`、`cumulativeValue`、`cumulativeYoy`、`unit`。

## 使用注意事项

1. **统计时间格式**：`statTime` 严格限定为单月格式 `YYYY-MM`（如 `2025-01`、`2026-04`），不支持 `YYYY`、`YYYY-MM-DD` 或 `1-2月` 这类区间字符串。全部九个 Tool 均要求必填 `statTime`。
2. **春节合并月处理**：交通运输月度统计在年初可能存在 1、2 月合并发布到 2 月的情况。若查询 `YYYY-01` 返回空结果，可尝试查询 `YYYY-02` 并核对返回记录中的 `statTime`（如 `"2月"`、`"1-2月"`）。
3. **地区类型枚举**：支持地区维度的四个统计 Tool（公路水路、城市客运、港口、交通投资）仅接受 `regionType` 为 `country` 或 `province`，不支持直接按城市名称筛选。
4. **字段与单位语义**：不同指标字典中的同比增长字段名存在差异（如 `yoyGrowth`、`currentYoy`/`cumulativeYoy`、`currentYoyGrowth`/`cumulativeYoyGrowth`、`momGrowth`），部分细项字段（如公路水路周转量、内河/沿海投资、邮政普遍服务细项）按上游统计期或地区披露情况返回，请按返回字段及 `unit` 原样读取，不改写正负号或零值。
5. **统一响应**：九个 Tool 成功时均统一返回 `total/resultList`，保留上游扩展字段。
6. **空结果边界**：空响应只表示当前统计期或地区维度未返回记录，不能据此推断当期无运价变化或无运输活动。
7. **能力边界**：本服务是按请求查询的只读接口，不提供运价预测、运力调度或投资收益评估。

## 使用提问示例

### 运价指数查询

1. 查询 `2026-04` 的沿海散货运价指数，对比煤炭、金属矿石和原油运价指数的环比变化
2. 查询 `2026-04` 的出口集装箱运价指数，查看美西、美东、欧洲和东南亚航线的当月值与累计均值
3. 查询 `2025-01` 与 `2025-02` 的沿海散货运价指数，对比年初两个月的综合指数及分品类变化

### 运输量与吞吐量统计

1. 查询 `2026-04` 全国公路水路运输统计（`regionType="country"`），对比公路与水路货物运输量的当期值、累计值及同比增长
2. 若 `2026-01` 全国公路水路运输统计返回为空，改查 `2026-02` 核对数据
3. 查询 `2026-04` 各省份港口货物吞吐量和集装箱吞吐量（`regionType="province"`）
4. 查询 `2026-04` 铁路运输统计与民航运输统计，比较客运周转量和航线结构变化
5. 查询 `2026-04` 邮政行业寄递业务量以及同城、异地、国际及港澳台快递量的同比增速
6. 查询 `2026-04` 全国城市轨道交通与公共汽电车客运量

### 交通运输投资统计

1. 查询 `2026-04` 全国公路水路建设投资、公路建设投资与水运建设投资的累计值及累计同比（`regionType="country"`）
2. 查询各省份 `2026-04` 的公路建设投资与公路水路建设投资分布（`regionType="province"`，部分省份含水运建设投资）

## 测试验证

离线测试不需要真实凭据：

```bash
python -m py_compile server/mcp_server.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

真实接口 smoke 测试必须显式传入 `--live`，并通过实际 MCP STDIO 会话完成初始化、Tool 调用和响应检查：

```bash
python tests/live_api_smoke.py --live
```

如需读取其他环境文件或指定测试月份，可显式指定：

```bash
python tests/live_api_smoke.py --live --env-file /path/to/transport.env --stat-time 2026-04
```

显式指定 `--env-file` 时，脚本只在内存中读取该凭据文件，不复制到服务目录；文件中的值会写入测试子进程环境，并优先于同名当前环境变量。不要提交凭据文件。

smoke 测试只应输出去标识化的记录数量、字段名和延迟，不输出业务记录内容、请求签名或凭据。空结果是合法接口结果，测试应标记“未取得非空样本”，不能据此判断业务上没有变化。

## 常见问题

### 没有配置认证信息

Tool 会返回 `INTEGRATOR_ID 未配置`、`SECRET_ID 未配置` 或 `SECRET_KEY 未配置`。在本服务目录配置 `.env`，或通过启动进程 / MCP 客户端的环境变量注入；不要把真实凭据写入 README 或提交到仓库。

### 已配置凭据，但上游仍返回业务错误

确认当前 HandaaS 对接器已经开通本 README 所列 9 个交通大数据产品权限。服务会保留上游业务错误的 `code` 和消息；产品未授权时不要修改 Product ID、签名逻辑或伪造空结果。

### 参数被拒绝

`statTime` 必须严格使用单月格式 `YYYY-MM`（如 `2025-01`）；`regionType` 仅支持 `country` 或 `province`。不要传入 `YYYY-MM-DD`、`1-2月` 或其他地区字符串。

### 返回 405 或 HTML 响应

检查 `console.handaas.com` 的 DNS、PAC / 透明代理规则，以及网络是否允许向网关发送 POST。该诊断只说明连接路径需要排查，不代表凭据或产品权限有效。

### 本地端口冲突

为 `sse` 或 `streamable-http` 设置一个未占用的 `FASTMCP_PORT`，然后同步修改客户端 URL。`stdio` 不需要 HTTP 监听端口。

## 接口资料依据

接口字段与产品 ID 依据父工作区 `doc/数据接口配置/data_product.json`、`doc/数据接口配置/data_field.json` 与服务源码整理。
