"""HandaaS 交通大数据 MCP 服务。"""

import json
import math
import os
import re
import sys
from hashlib import md5
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _server_port() -> int:
    """显式传入端口，避免 FastMCP 构造函数默认值覆盖环境配置。"""
    try:
        port = int(os.environ.get("FASTMCP_PORT", "8000"))
    except ValueError:
        raise ValueError("FASTMCP_PORT 必须为1到65535之间的整数") from None
    if not 1 <= port <= 65535:
        raise ValueError("FASTMCP_PORT 必须为1到65535之间的整数")
    return port


mcp = FastMCP(
    "交通大数据",
    instructions=(
        "提供沿海散货和出口集装箱运价指数查询，以及公路水路、铁路、民航、邮政、"
        "城市客运、港口、交通运输投资统计明细查询。"
        "所有工具均要求必填 statTime，且仅接受单月格式 YYYY-MM（如 2025-01），"
        "若 1 月数据为空可尝试查询 2 月（存在 1-2 月合并发布情况）；"
        "regionType 可选，仅接受 country（全国）或 province（省份）。"
        "保留上游原始数值、正负增长、零值与单位，空结果不代表无运价波动或无运输活动；本服务只读查询，不做趋势预测。"
    ),
    dependencies=["python-dotenv", "requests"],
    host="127.0.0.1",
    port=_server_port(),
)

GATEWAY_BASE_URL = "https://console.handaas.com/api/v1/integrator/call_api"
DEFAULT_TIMEOUT_SECONDS = 30.0
PRODUCT_IDS = {
    "coastal_bulk_freight_index": "6a704e0d61c110074d34228f",
    "export_container_freight_index": "6a705029c125d8e5a37c2956",
    "highway_waterway_statistics": "6a705750c125d8e5a37c2993",
    "railway_statistics": "6a705b6961c110074d34242f",
    "civil_aviation_statistics": "6a705c7261c110074d3424a2",
    "postal_statistics": "6a705ee4c125d8e5a37c2a70",
    "urban_passenger_statistics": "6a70603cc125d8e5a37c2a93",
    "port_statistics": "6a706148c125d8e5a37c2b18",
    "transport_investment_statistics": "6a70617f61c110074d342595",
}
READ_ONLY_TOOL = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
StatTimeRequired = Annotated[
    str,
    Field(
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description='统计时间，必填，单月格式 YYYY-MM，如 "2025-01"；若1月为空可尝试查询2月',
    ),
]
RegionType = Literal["country", "province"]

_STAT_TIME_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DOMAIN_LIST_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("hwWayList", ("hwWayCount", "hwWayount")),
    ("railwayList", ("railwayCount",)),
    ("civilAviaList", ("civilAviaCount",)),
    ("postalList", ("postalCount",)),
    ("urPassengerList", ("urPassengerCount",)),
    ("portList", ("portCount",)),
    ("investList", ("investCount",)),
)


def _request_timeout() -> float:
    try:
        value = float(os.environ.get("HANDAAS_REQUEST_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if math.isfinite(value) and value > 0 else DEFAULT_TIMEOUT_SECONDS


def _credential(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value if value and not value.startswith("your_") else None


def _compact_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def _build_signature(call_params: dict[str, str], secret_key: str) -> str:
    plain = "".join(str(call_params[key]) for key in sorted(call_params))
    return md5(f"{plain}{secret_key}".encode("utf-8")).hexdigest()


def call_api(product_id: str, params: dict[str, Any]) -> Any:
    """沿用项目的 Integrator Gateway 签名协议，不输出凭据或真实响应。"""
    credentials = {name: _credential(name) for name in ("INTEGRATOR_ID", "SECRET_ID", "SECRET_KEY")}
    for name, value in credentials.items():
        if not value:
            return {"error": f"{name} 未配置"}
    if not product_id:
        return {"error": "Product ID 不能为空"}
    integrator_id = cast(str, credentials["INTEGRATOR_ID"])
    call_params = {
        "product_id": product_id,
        "secret_id": cast(str, credentials["SECRET_ID"]),
        "params": json.dumps(_compact_params(params), ensure_ascii=False, separators=(",", ":")),
    }
    call_params["signature"] = _build_signature(call_params, cast(str, credentials["SECRET_KEY"]))
    url = f"{GATEWAY_BASE_URL}/{quote(integrator_id, safe='')}"
    try:
        response = requests.post(url, data=call_params, timeout=_request_timeout())
    except requests.RequestException:
        return {"error": "HandaaS 网关请求失败，请稍后重试"}
    if response.status_code != 200:
        result: dict[str, Any] = {"error": "HandaaS 网关返回非成功状态", "statusCode": response.status_code}
        if response.status_code == 405 and "text/html" in response.headers.get("content-type", "").lower():
            result["diagnostic"] = "请检查 console.handaas.com 的 DNS、PAC/透明代理规则和 POST 放行情况"
        return result
    try:
        payload = response.json()
    except ValueError:
        return {"error": "HandaaS 网关返回了无法解析的响应"}
    if not isinstance(payload, dict):
        return {"error": "HandaaS 网关返回格式异常"}
    code = payload.get("code")
    message = payload.get("msgCN") or payload.get("message")
    if str(code) == "10001":
        return {"total": 0, "resultList": []}
    if code is not None and str(code) not in {"1", "10000"}:
        return {"error": message or "HandaaS 网关返回业务错误", "code": code}
    if "data" in payload:
        return payload["data"]
    if message == "查询数据为空":
        return {"total": 0, "resultList": []}
    result = {"error": message or "HandaaS 网关未返回 data"}
    if code is not None:
        result["code"] = code
    return result


def _unwrap_backend_data(result: Any) -> Any:
    """兼容业务 data 及内部 stat/data 外层，保留上游错误。"""
    if not isinstance(result, dict) or "error" in result or "stat" not in result:
        return result
    if result.get("stat") != 1:
        return {"error": result.get("msg") or "上游数据接口返回失败", "code": result.get("err")}
    return result.get("data")


def _validate_stat_time(stat_time: str | None, *, required: bool = False) -> tuple[str | None, dict[str, Any] | None]:
    """校验并规范化 statTime，仅支持单月格式 YYYY-MM。"""
    if stat_time is None:
        if required:
            return None, {
                "error": "统计时间不能为空，仅支持单月格式 YYYY-MM，如 2025-01",
                "parameter": "statTime",
                "code": "INVALID_STAT_TIME",
            }
        return None, None
    normalized = str(stat_time).strip()
    if not normalized or not _STAT_TIME_RE.fullmatch(normalized):
        return None, {
            "error": "统计时间格式不合法，仅支持单月格式 YYYY-MM，如 2025-01",
            "parameter": "statTime",
            "code": "INVALID_STAT_TIME",
        }
    return normalized, None


def _validate_region_type(region_type: str | None) -> tuple[str | None, dict[str, Any] | None]:
    """校验并规范化 regionType，仅支持 country 或 province。"""
    if region_type is None:
        return None, None
    normalized = str(region_type).strip()
    if normalized not in {"country", "province"}:
        return None, {
            "error": "regionType 仅支持 country（全国）或 province（省份）",
            "parameter": "regionType",
            "code": "INVALID_REGION_TYPE",
        }
    return normalized, None


def _normalize_result(result: Any) -> dict[str, Any]:
    """统一标准化 dataList/resultList/领域明细列表与单对象响应，保留上游字段与错误。"""
    result = _unwrap_backend_data(result)
    if isinstance(result, list):
        return {"total": len(result), "resultList": result}
    if not isinstance(result, dict):
        return {"error": "上游交通数据格式异常"}
    if "error" in result:
        return result
    if isinstance(result.get("resultList"), list):
        records = result["resultList"]
        total = result.get("total", len(records))
        return {"total": total, "resultList": records}
    if isinstance(result.get("dataList"), list):
        records = result["dataList"]
        total = result.get("dataTotal", result.get("dataCount", len(records)))
        return {"total": total, "resultList": records}
    for list_key, count_keys in _DOMAIN_LIST_KEYS:
        if isinstance(result.get(list_key), list):
            records = result[list_key]
            total = next(
                (result[key] for key in count_keys if isinstance(result.get(key), int)),
                len(records),
            )
            return {"total": total, "resultList": records}
    if not result:
        return {"total": 0, "resultList": []}
    return {"total": 1, "resultList": [result]}


@mcp.tool(
    title="沿海散货运价指数查询",
    description=(
        "查询沿海（散货）运价指数，返回综合指数及煤炭、金属矿石、粮食、成品油、原油运价指数的"
        "去年同期值、当年累计均值、当月值和环比增长。statTime 必填且仅接受单月格式 YYYY-MM（如 2025-01）；"
        "若1月数据为空可尝试取2月（存在1、2月数据合并发布到2月的情况）。返回 total 与 resultList，保留原始数值与正负号。"
    ),
    annotations=READ_ONLY_TOOL,
)
def transport_coastal_bulk_freight_index(statTime: StatTimeRequired) -> dict[str, Any]:
    """按统计月份查询沿海散货运价指数及分品类环比增长。"""
    stat_time, error = _validate_stat_time(statTime, required=True)
    if error:
        return error
    return _normalize_result(
        call_api(PRODUCT_IDS["coastal_bulk_freight_index"], {"statTime": stat_time})
    )


@mcp.tool(
    title="出口集装箱运价指数查询",
    description=(
        "查询出口集装箱运价指数，返回综合指数及欧洲、地中海、美西、美东、波红、澳新、西非、南非、"
        "南美、日本、东南亚、韩国等航线运价指数的去年同期值、当年累计均值、当月值和环比增长。"
        "statTime 必填且仅接受单月格式 YYYY-MM（如 2025-01）；若1月数据为空可尝试取2月。"
        "返回 total 与 resultList，保留原始数值与正负号。"
    ),
    annotations=READ_ONLY_TOOL,
)
def transport_export_container_freight_index(statTime: StatTimeRequired) -> dict[str, Any]:
    """按统计月份查询出口集装箱综合指数及各主要航线运价指数。"""
    stat_time, error = _validate_stat_time(statTime, required=True)
    if error:
        return error
    return _normalize_result(
        call_api(PRODUCT_IDS["export_container_freight_index"], {"statTime": stat_time})
    )


@mcp.tool(
    title="公路水路运输统计",
    description=(
        "查询公路/水路旅客与货物运输量及周转量统计（部分时期或地区可能仅返回客货运输量等已披露指标），"
        "包含当期值、累计值、同比增长与单位，支持按全国/省份维度筛选。"
        "statTime 必填且仅接受单月格式 YYYY-MM（若1月为空可尝试2月）；regionType 可选，仅支持 country 或 province。"
        "返回 total 与 resultList，保留统计月份（如 5月、1-2月）和统计周期。"
    ),
    annotations=READ_ONLY_TOOL,
)
def transport_highway_waterway_statistics(
    statTime: StatTimeRequired,
    regionType: RegionType | None = None,
) -> dict[str, Any]:
    """查询全国或分省公路、水路客货运输量与周转量统计明细。"""
    stat_time, error = _validate_stat_time(statTime, required=True)
    if error:
        return error
    region_type, error = _validate_region_type(regionType)
    if error:
        return error
    return _normalize_result(
        call_api(
            PRODUCT_IDS["highway_waterway_statistics"],
            _compact_params({"statTime": stat_time, "regionType": region_type}),
        )
    )


@mcp.tool(
    title="铁路运输统计",
    description=(
        "查询铁路旅客发送量/周转量、货运总发送量与货物发送量、货运总周转量与货物周转量及铁路固定资产投资数据，"
        "包含当期值、累计值、当期同比增长、累计同比增长和单位。"
        "statTime 必填且仅接受单月格式 YYYY-MM（若1月为空可尝试2月）。返回 total 与 resultList。"
    ),
    annotations=READ_ONLY_TOOL,
)
def transport_railway_statistics(statTime: StatTimeRequired) -> dict[str, Any]:
    """查询铁路客货运输量、周转量及固定资产投资统计明细。"""
    stat_time, error = _validate_stat_time(statTime, required=True)
    if error:
        return error
    return _normalize_result(
        call_api(PRODUCT_IDS["railway_statistics"], {"statTime": stat_time})
    )


@mcp.tool(
    title="民航运输统计",
    description=(
        "查询民航旅客运输量、运输总周转量、货邮运输量及飞行效率（客座率），"
        "前三项均按总计（total）、国内航线（domesticRoute）、港澳台航线（hkMacaoTaiwanRoute）与国际航线（internationalRoute）拆分。"
        "statTime 必填且仅接受单月格式 YYYY-MM（若1月为空可尝试2月）。返回 total 与 resultList。"
    ),
    annotations=READ_ONLY_TOOL,
)
def transport_civil_aviation_statistics(statTime: StatTimeRequired) -> dict[str, Any]:
    """查询民航客货邮运输量、总周转量及客座率统计明细。"""
    stat_time, error = _validate_stat_time(statTime, required=True)
    if error:
        return error
    return _normalize_result(
        call_api(PRODUCT_IDS["civil_aviation_statistics"], {"statTime": stat_time})
    )


@mcp.tool(
    title="邮政运输统计",
    description=(
        "查询邮政行业业务收入、快递业务收入、邮政普遍服务业务收入、寄递业务量、快递业务量"
        "（同城/异地/国际及港澳台）及函件、包裹、订销报纸杂志、汇兑等统计明细（部分普遍服务细项按统计期披露）。"
        "statTime 必填且仅接受单月格式 YYYY-MM（若1月为空可尝试2月）。返回 total 与 resultList。"
    ),
    annotations=READ_ONLY_TOOL,
)
def transport_postal_statistics(statTime: StatTimeRequired) -> dict[str, Any]:
    """查询邮政行业收入、快递量结构及普遍服务统计明细。"""
    stat_time, error = _validate_stat_time(statTime, required=True)
    if error:
        return error
    return _normalize_result(
        call_api(PRODUCT_IDS["postal_statistics"], {"statTime": stat_time})
    )


@mcp.tool(
    title="城市客运统计",
    description=(
        "查询城市客运总量及公共汽电车、出租汽车、城市轨道交通、轮渡的客运量，"
        "包含当期值、累计值、当期同比、累计同比和单位，支持按全国/省份维度筛选。"
        "statTime 必填且仅接受单月格式 YYYY-MM（若1月为空可尝试2月）；regionType 可选，仅支持 country 或 province。"
        "返回 total 与 resultList。"
    ),
    annotations=READ_ONLY_TOOL,
)
def transport_urban_passenger_statistics(
    statTime: StatTimeRequired,
    regionType: RegionType | None = None,
) -> dict[str, Any]:
    """查询全国或分省城市公共交通客运量及分方式明细。"""
    stat_time, error = _validate_stat_time(statTime, required=True)
    if error:
        return error
    region_type, error = _validate_region_type(regionType)
    if error:
        return error
    return _normalize_result(
        call_api(
            PRODUCT_IDS["urban_passenger_statistics"],
            _compact_params({"statTime": stat_time, "regionType": region_type}),
        )
    )


@mcp.tool(
    title="港口运输统计",
    description=(
        "查询港口货物吞吐量、外贸货物吞吐量和集装箱吞吐量，包含当期值、累计值、累计同比和单位，支持按全国/省份维度筛选。"
        "statTime 必填且仅接受单月格式 YYYY-MM（若1月为空可尝试2月）；regionType 可选，仅支持 country 或 province。"
        "返回 total 与 resultList。"
    ),
    annotations=READ_ONLY_TOOL,
)
def transport_port_statistics(
    statTime: StatTimeRequired,
    regionType: RegionType | None = None,
) -> dict[str, Any]:
    """查询全国或分省港口货物、外贸货物及集装箱吞吐量统计。"""
    stat_time, error = _validate_stat_time(statTime, required=True)
    if error:
        return error
    region_type, error = _validate_region_type(regionType)
    if error:
        return error
    return _normalize_result(
        call_api(
            PRODUCT_IDS["port_statistics"],
            _compact_params({"statTime": stat_time, "regionType": region_type}),
        )
    )


@mcp.tool(
    title="交通运输投资统计",
    description=(
        "查询公路水路建设投资及公路、水运、内河、沿海建设投资数据（部分时期或省份仅返回已披露的公路水路、公路及水运投资指标），"
        "包含当期值、累计值、累计同比和单位，支持按全国/省份维度筛选。"
        "statTime 必填且仅接受单月格式 YYYY-MM（若1月为空可尝试2月）；regionType 可选，仅支持 country 或 province。"
        "返回 total 与 resultList。"
    ),
    annotations=READ_ONLY_TOOL,
)
def transport_investment_statistics(
    statTime: StatTimeRequired,
    regionType: RegionType | None = None,
) -> dict[str, Any]:
    """查询全国或分省公路水路固定资产建设投资统计明细。"""
    stat_time, error = _validate_stat_time(statTime, required=True)
    if error:
        return error
    region_type, error = _validate_region_type(regionType)
    if error:
        return error
    return _normalize_result(
        call_api(
            PRODUCT_IDS["transport_investment_statistics"],
            _compact_params({"statTime": stat_time, "regionType": region_type}),
        )
    )


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    transport = arguments[0] if arguments else "stdio"
    if transport not in {"stdio", "sse", "streamable-http"}:
        print("启动方式必须是 stdio、sse 或 streamable-http", file=sys.stderr)
        return 2
    mcp.run(transport=cast(Literal["stdio", "sse", "streamable-http"], transport))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
