#!/usr/bin/env python3
"""显式启用后通过真实 MCP STDIO 验证九个只读接口，仅输出脱敏结构摘要。"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]


def _cases(stat_time: str) -> tuple[tuple[str, dict[str, Any], set[str]], ...]:
    return (
        (
            "transport_coastal_bulk_freight_index",
            {"statTime": stat_time},
            {"year", "statTime", "coastalBulkFreightIndex"},
        ),
        (
            "transport_export_container_freight_index",
            {"statTime": stat_time},
            {"year", "statTime", "exportContainerCompositeIndex"},
        ),
        (
            "transport_highway_waterway_statistics",
            {"statTime": stat_time, "regionType": "country"},
            {"year", "statTime", "roadFreightVolume", "waterFreightVolume"},
        ),
        (
            "transport_railway_statistics",
            {"statTime": stat_time},
            {"year", "statTime", "passengerDispatchVolume", "freightDispatchVolume"},
        ),
        (
            "transport_civil_aviation_statistics",
            {"statTime": stat_time},
            {"year", "statTime", "passengerVolume", "transportTurnover"},
        ),
        (
            "transport_postal_statistics",
            {"statTime": stat_time},
            {"year", "statTime", "postalIndustryBusinessIncome", "expressBusinessVolume"},
        ),
        (
            "transport_urban_passenger_statistics",
            {"statTime": stat_time, "regionType": "country"},
            {"year", "statTime", "urbanTransportVolume", "urbanRailTransitVolume"},
        ),
        (
            "transport_port_statistics",
            {"statTime": stat_time, "regionType": "country"},
            {"year", "statTime", "cargoThroughput", "containerThroughput"},
        ),
        (
            "transport_investment_statistics",
            {"statTime": stat_time, "regionType": "country"},
            {"year", "statTime", "highwayWaterwayConstructionInvestment"},
        ),
    )


def _summary(tool: str, result: Any, required: set[str]) -> dict[str, Any]:
    """不输出业务记录、原始错误文本、请求参数、凭据或标识。"""
    row: dict[str, Any] = {"tool": tool, "passed": False}
    if not isinstance(result, dict) or "error" in result:
        row["reason"] = "upstream_error_or_invalid_object"
        return row
    records = result.get("resultList")
    if type(result.get("total")) is not int or result["total"] < 0 or not isinstance(records, list):
        row["reason"] = "invalid_total_or_result_list"
        return row
    if any(not isinstance(record, dict) or not required.issubset(record) for record in records):
        row["reason"] = "documented_record_fields_missing"
        return row
    row.update(
        passed=True,
        total=result["total"],
        resultCount=len(records),
        nonemptySampleValidated=bool(records),
        validatedFields=sorted(required) if records else [],
    )
    return row


async def _run(env: dict[str, str], stat_time: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cases = _cases(stat_time)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "server/mcp_server.py"), "stdio"],
        env=env,
        cwd=str(ROOT),
    )
    with open(os.devnull, "w") as error_log:
        async with stdio_client(params, errlog=error_log) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                if initialized.serverInfo.name != "交通大数据":
                    raise RuntimeError("unexpected_server")
                if {tool.name for tool in tools.tools} != {case[0] for case in cases}:
                    raise RuntimeError("unexpected_tool_set")
                for name, arguments, required in cases:
                    started = time.perf_counter()
                    try:
                        result = await session.call_tool(name, arguments)
                        if result.isError:
                            row = {"tool": name, "passed": False, "reason": "mcp_tool_error"}
                        else:
                            row = _summary(name, result.structuredContent, required)
                    except Exception:
                        row = {"tool": name, "passed": False, "reason": "mcp_request_failed"}
                    row["latencyMs"] = round((time.perf_counter() - started) * 1000)
                    results.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="确认调用已开通的真实只读数据产品，可能消耗额度")
    parser.add_argument("--env-file", type=Path, help="可选凭据文件，仅在内存读取，不复制或写入服务目录")
    parser.add_argument("--stat-time", default="2026-04", help="统计月份，格式 YYYY-MM，默认 2026-04")
    args = parser.parse_args(argv)
    if not args.live:
        parser.error("真实 API 测试需要显式传入 --live")
    env = dict(os.environ)
    env_file = args.env_file if args.env_file is not None else ROOT / ".env"
    if args.env_file is not None and not env_file.is_file():
        print("配置错误：指定的环境文件不存在", file=sys.stderr)
        return 2
    if env_file.is_file():
        for key, value in dotenv_values(env_file).items():
            if value is not None and (args.env_file is not None or key not in env):
                env[key] = value
    for key in ("INTEGRATOR_ID", "SECRET_ID", "SECRET_KEY"):
        value = env.get(key, "").strip()
        if not value or value.startswith("your_"):
            print(f"配置错误：{key} 未配置", file=sys.stderr)
            return 2
    logging.disable(logging.CRITICAL)
    try:
        results = asyncio.run(_run(env, args.stat_time))
    except Exception:
        print("MCP 验证未完成：请检查服务启动、依赖及连接配置", file=sys.stderr)
        return 1
    failed = sum(not row["passed"] for row in results)
    print(
        json.dumps(
            {
                "toolCallCount": len(results),
                "passed": len(results) - failed,
                "failed": failed,
                "emptySamples": sum(row.get("nonemptySampleValidated") is False for row in results),
            },
            ensure_ascii=False,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
