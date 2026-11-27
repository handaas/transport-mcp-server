"""交通大数据 MCP 服务离线契约测试。"""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
from typing import Any
from unittest import TestCase
from unittest.mock import Mock, patch

import requests
from mcp.server.fastmcp.exceptions import ToolError


SERVER_PATH = Path(__file__).parents[1] / "server" / "mcp_server.py"
SPEC = importlib.util.spec_from_file_location("transport_mcp_server", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


FREIGHT_INDEX_TOOLS = (
    "transport_coastal_bulk_freight_index",
    "transport_export_container_freight_index",
)
REGIONAL_STAT_TOOLS = (
    "transport_highway_waterway_statistics",
    "transport_urban_passenger_statistics",
    "transport_port_statistics",
    "transport_investment_statistics",
)
NATIONAL_STAT_TOOLS = (
    "transport_railway_statistics",
    "transport_civil_aviation_statistics",
    "transport_postal_statistics",
)
ALL_TOOLS = FREIGHT_INDEX_TOOLS + REGIONAL_STAT_TOOLS + NATIONAL_STAT_TOOLS


class ContractTests(TestCase):
    def test_registered_tools_have_read_only_contract(self) -> None:
        tools = asyncio.run(server.mcp.list_tools())
        self.assertEqual(server.mcp.name, "交通大数据")
        self.assertEqual({tool.name for tool in tools}, set(ALL_TOOLS))
        for tool in tools:
            with self.subTest(tool=tool.name):
                self.assertEqual(tool.outputSchema.get("type"), "object")
                self.assertTrue(tool.annotations.readOnlyHint)
                self.assertFalse(tool.annotations.destructiveHint)
                self.assertTrue(tool.annotations.idempotentHint)
                self.assertTrue(tool.annotations.openWorldHint)
                self.assertGreaterEqual(len(tool.description or ""), 40)

    def test_product_ids_match_catalog(self) -> None:
        self.assertEqual(len(server.PRODUCT_IDS), 9)
        self.assertEqual(
            set(server.PRODUCT_IDS.values()),
            {
                "6a704e0d61c110074d34228f",
                "6a705029c125d8e5a37c2956",
                "6a705750c125d8e5a37c2993",
                "6a705b6961c110074d34242f",
                "6a705c7261c110074d3424a2",
                "6a705ee4c125d8e5a37c2a70",
                "6a70603cc125d8e5a37c2a93",
                "6a706148c125d8e5a37c2b18",
                "6a70617f61c110074d342595",
            },
        )

    def test_schemas_expose_only_documented_parameters(self) -> None:
        tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
        for name in FREIGHT_INDEX_TOOLS:
            with self.subTest(tool=name):
                schema = tools[name].inputSchema
                self.assertEqual(set(schema["properties"]), {"statTime"})
                self.assertEqual(schema.get("required"), ["statTime"])

        for name in REGIONAL_STAT_TOOLS:
            with self.subTest(tool=name):
                schema = tools[name].inputSchema
                self.assertEqual(set(schema["properties"]), {"statTime", "regionType"})
                self.assertEqual(schema.get("required"), ["statTime"])
                serialized = json.dumps(schema["properties"]["regionType"], ensure_ascii=False)
                self.assertIn("country", serialized)
                self.assertIn("province", serialized)

        for name in NATIONAL_STAT_TOOLS:
            with self.subTest(tool=name):
                schema = tools[name].inputSchema
                self.assertEqual(set(schema["properties"]), {"statTime"})
                self.assertEqual(schema.get("required"), ["statTime"])

    def test_mcp_dispatch_returns_structured_result_and_enforces_schema(self) -> None:
        async def check() -> None:
            with patch.object(
                server,
                "call_api",
                return_value={"dataList": [{"year": 2026, "statTime": "4月"}], "dataTotal": 1},
            ) as call:
                _, structured = await server.mcp.call_tool(
                    "transport_coastal_bulk_freight_index", {"statTime": "2026-04"}
                )
            self.assertEqual(
                structured,
                {"total": 1, "resultList": [{"year": 2026, "statTime": "4月"}]},
            )
            call.assert_called_once_with("6a704e0d61c110074d34228f", {"statTime": "2026-04"})

            invalid_cases = (
                ("transport_coastal_bulk_freight_index", {"statTime": "2026-13"}),
                ("transport_export_container_freight_index", {"statTime": "2026-04-01"}),
                ("transport_railway_statistics", {}),
                ("transport_port_statistics", {"regionType": "country"}),
                ("transport_port_statistics", {"statTime": "2026-04", "regionType": "city"}),
            )
            for tool_name, arguments in invalid_cases:
                with self.subTest(tool=tool_name, arguments=arguments), patch.object(
                    server, "call_api"
                ) as call:
                    with self.assertRaises(ToolError):
                        await server.mcp.call_tool(tool_name, arguments)
                    call.assert_not_called()

        asyncio.run(check())


class GatewayTests(TestCase):
    def test_credentials_are_trimmed_and_placeholders_are_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"INTEGRATOR_ID": "  tenant  ", "SECRET_ID": "your_secret", "SECRET_KEY": " "},
            clear=True,
        ):
            self.assertEqual(server._credential("INTEGRATOR_ID"), "tenant")
            self.assertIsNone(server._credential("SECRET_ID"))
            self.assertIsNone(server._credential("SECRET_KEY"))

    def test_missing_credentials_prevent_network_access(self) -> None:
        credentials: tuple[tuple[dict[str, str], str], ...] = (
            ({}, "INTEGRATOR_ID"),
            ({"INTEGRATOR_ID": "i"}, "SECRET_ID"),
            ({"INTEGRATOR_ID": "i", "SECRET_ID": "s"}, "SECRET_KEY"),
        )
        for environment, missing in credentials:
            with self.subTest(missing=missing), patch.dict(
                os.environ, environment, clear=True
            ), patch.object(server.requests, "post") as post:
                result = server.call_api("product", {})
            self.assertIn(missing, result["error"])
            post.assert_not_called()

    def test_gateway_posts_compact_signed_payload(self) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {"code": "10000", "data": {"dataList": [], "dataTotal": 0}}
        credentials = {
            "INTEGRATOR_ID": "test/integrator",
            "SECRET_ID": "test-secret-id",
            "SECRET_KEY": "test-secret-key",
        }
        with patch.dict(os.environ, credentials, clear=True), patch.object(
            server.requests, "post", return_value=response
        ) as post:
            result = server.call_api("product", {"statTime": "2026-04", "regionType": None})
        self.assertEqual(result, {"dataList": [], "dataTotal": 0})
        self.assertEqual(post.call_args.args[0], server.GATEWAY_BASE_URL + "/test%2Fintegrator")
        payload = post.call_args.kwargs["data"]
        self.assertEqual(json.loads(payload["params"]), {"statTime": "2026-04"})
        unsigned = {key: value for key, value in payload.items() if key != "signature"}
        self.assertEqual(payload["signature"], server._build_signature(unsigned, "test-secret-key"))
        self.assertNotIn("test-secret-key", json.dumps(payload))

    def test_empty_and_business_errors_are_not_confused(self) -> None:
        credentials = {
            "INTEGRATOR_ID": "integrator",
            "SECRET_ID": "secret-id",
            "SECRET_KEY": "secret-key",
        }
        cases = (
            ({"code": "10001", "msgCN": "查询数据为空"}, {"total": 0, "resultList": []}),
            ({"msgCN": "查询数据为空"}, {"total": 0, "resultList": []}),
            (
                {"code": "403", "msgCN": "未开通数据产品", "data": None},
                {"error": "未开通数据产品", "code": "403"},
            ),
        )
        for payload, expected in cases:
            response = Mock(status_code=200)
            response.json.return_value = payload
            with self.subTest(payload=payload), patch.dict(
                os.environ, credentials, clear=True
            ), patch.object(server.requests, "post", return_value=response):
                self.assertEqual(server.call_api("product", {}), expected)

    def test_transport_failures_are_actionable_and_do_not_leak_secrets(self) -> None:
        credentials = {
            "INTEGRATOR_ID": "integrator",
            "SECRET_ID": "sensitive-id",
            "SECRET_KEY": "sensitive-key",
        }
        response_405 = Mock(status_code=405)
        response_405.headers = {"content-type": "text/html; charset=utf-8"}
        response_500 = Mock(status_code=500)
        response_500.headers = {"content-type": "application/json"}
        response_bad_json = Mock(status_code=200)
        response_bad_json.json.side_effect = ValueError("secret response body")
        cases: tuple[Any, ...] = (
            requests.Timeout("sensitive-key"),
            response_405,
            response_500,
            response_bad_json,
        )
        for outcome in cases:
            with self.subTest(outcome=type(outcome).__name__), patch.dict(
                os.environ, credentials, clear=True
            ), patch.object(
                server.requests,
                "post",
                side_effect=outcome if isinstance(outcome, Exception) else None,
                return_value=None if isinstance(outcome, Exception) else outcome,
            ):
                result = server.call_api("product", {})
            self.assertIn("error", result)
            self.assertNotIn("sensitive-id", json.dumps(result, ensure_ascii=False))
            self.assertNotIn("sensitive-key", json.dumps(result, ensure_ascii=False))
        with patch.dict(os.environ, credentials, clear=True), patch.object(
            server.requests, "post", return_value=response_405
        ):
            diag = server.call_api("product", {})
        self.assertIn("diagnostic", diag)

    def test_request_timeout_and_port_validation(self) -> None:
        with patch.dict(os.environ, {"HANDAAS_REQUEST_TIMEOUT": "2.5"}, clear=True):
            self.assertEqual(server._request_timeout(), 2.5)
        for value in ("0", "-1", "nan", "invalid"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"HANDAAS_REQUEST_TIMEOUT": value}, clear=True
            ):
                self.assertEqual(server._request_timeout(), server.DEFAULT_TIMEOUT_SECONDS)
        for bad_port in ("0", "65536", "abc"):
            with self.subTest(port=bad_port), patch.dict(
                os.environ, {"FASTMCP_PORT": bad_port}, clear=True
            ):
                with self.assertRaises(ValueError):
                    server._server_port()


class RoutingAndNormalizationTests(TestCase):
    def test_freight_index_tools_route_and_validate_required_stat_time(self) -> None:
        routes = {
            "transport_coastal_bulk_freight_index": "6a704e0d61c110074d34228f",
            "transport_export_container_freight_index": "6a705029c125d8e5a37c2956",
        }
        for name, product_id in routes.items():
            with self.subTest(tool=name), patch.object(
                server, "call_api", return_value={"dataList": [{"year": 2026}], "dataTotal": 1}
            ) as call:
                result = getattr(server, name)(" 2026-04 ")
            self.assertEqual(result, {"total": 1, "resultList": [{"year": 2026}]})
            call.assert_called_once_with(product_id, {"statTime": "2026-04"})

            for bad in ("", "   ", "2026", "2026-00", "2026-13", "2026/04", "2026-04-01"):
                with self.subTest(tool=name, statTime=bad), patch.object(server, "call_api") as call:
                    err = getattr(server, name)(bad)
                self.assertEqual(err["parameter"], "statTime")
                self.assertEqual(err["code"], "INVALID_STAT_TIME")
                call.assert_not_called()

    def test_regional_statistics_tools_route_and_validate_filters(self) -> None:
        routes = {
            "transport_highway_waterway_statistics": "6a705750c125d8e5a37c2993",
            "transport_urban_passenger_statistics": "6a70603cc125d8e5a37c2a93",
            "transport_port_statistics": "6a706148c125d8e5a37c2b18",
            "transport_investment_statistics": "6a70617f61c110074d342595",
        }
        for name, product_id in routes.items():
            with self.subTest(tool=name, case="both"), patch.object(
                server, "call_api", return_value={"total": 0, "resultList": []}
            ) as call:
                result = getattr(server, name)(statTime=" 2026-04 ", regionType="province")
            self.assertEqual(result, {"total": 0, "resultList": []})
            call.assert_called_once_with(
                product_id, {"statTime": "2026-04", "regionType": "province"}
            )

            with self.subTest(tool=name, case="stat_time_only"), patch.object(
                server, "call_api", return_value={"total": 0, "resultList": []}
            ) as call:
                getattr(server, name)(statTime="2026-04")
            call.assert_called_once_with(product_id, {"statTime": "2026-04"})

            for bad_args, param in (
                ({"statTime": None}, "statTime"),
                ({"statTime": "2026-13"}, "statTime"),
                ({"statTime": ""}, "statTime"),
                ({"statTime": "2026-04", "regionType": "city"}, "regionType"),
                ({"statTime": "2026-04", "regionType": ""}, "regionType"),
            ):
                with self.subTest(tool=name, bad_args=bad_args), patch.object(
                    server, "call_api"
                ) as call:
                    err = getattr(server, name)(**bad_args)
                self.assertEqual(err["parameter"], param)
                call.assert_not_called()

    def test_national_statistics_tools_route_and_validate_required_stat_time(self) -> None:
        routes = {
            "transport_railway_statistics": "6a705b6961c110074d34242f",
            "transport_civil_aviation_statistics": "6a705c7261c110074d3424a2",
            "transport_postal_statistics": "6a705ee4c125d8e5a37c2a70",
        }
        for name, product_id in routes.items():
            with self.subTest(tool=name, case="with_time"), patch.object(
                server, "call_api", return_value={"dataList": [{"year": 2026}], "dataCount": 1}
            ) as call:
                result = getattr(server, name)(statTime=" 2026-04 ")
            self.assertEqual(result, {"total": 1, "resultList": [{"year": 2026}]})
            call.assert_called_once_with(product_id, {"statTime": "2026-04"})

            for bad in (None, "", "2026-99"):
                with self.subTest(tool=name, statTime=bad), patch.object(server, "call_api") as call:
                    err = getattr(server, name)(statTime=bad)
                self.assertEqual(err["parameter"], "statTime")
                self.assertEqual(err["code"], "INVALID_STAT_TIME")
                call.assert_not_called()

    def test_normalizer_supports_all_documented_shapes_and_preserves_values(self) -> None:
        record = {
            "year": 2026,
            "statTime": "4月",
            "coastalBulkFreightIndex": {
                "lastYear": 1000.0,
                "currentYear": 0,
                "currentMonth": 995.2,
                "momGrowth": -0.8,
            },
        }
        cases = (
            ({"total": 2, "resultList": [record]}, {"total": 2, "resultList": [record]}),
            ({"dataTotal": 2, "dataList": [record]}, {"total": 2, "resultList": [record]}),
            ({"dataCount": 1, "dataList": [record]}, {"total": 1, "resultList": [record]}),
            ({"stat": 1, "data": {"dataTotal": 1, "dataList": [record]}}, {"total": 1, "resultList": [record]}),
            ({"hwWayount": 3, "hwWayList": [record]}, {"total": 3, "resultList": [record]}),
            ({"railwayCount": 1, "railwayList": [record]}, {"total": 1, "resultList": [record]}),
            ({"civilAviaCount": 1, "civilAviaList": [record]}, {"total": 1, "resultList": [record]}),
            ({"postalCount": 1, "postalList": [record]}, {"total": 1, "resultList": [record]}),
            ({"urPassengerCount": 1, "urPassengerList": [record]}, {"total": 1, "resultList": [record]}),
            ({"portCount": 1, "portList": [record]}, {"total": 1, "resultList": [record]}),
            ({"investCount": 1, "investList": [record]}, {"total": 1, "resultList": [record]}),
            ([record], {"total": 1, "resultList": [record]}),
            (record, {"total": 1, "resultList": [record]}),
            ({}, {"total": 0, "resultList": []}),
        )
        for upstream, expected in cases:
            with self.subTest(upstream=upstream):
                self.assertEqual(server._normalize_result(upstream), expected)

        error = {"error": "上游失败", "code": "403"}
        self.assertEqual(server._normalize_result(error), error)
