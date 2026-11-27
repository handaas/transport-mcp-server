"""使用真实 MCP 传输与合成上游响应测试，禁止访问 HandaaS。"""

import asyncio
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest import IsolatedAsyncioTestCase, TestCase

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location('transport_transport_fixture', sys.argv[1])
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
def forbidden_network(*args, **kwargs):
    raise AssertionError('Real upstream HTTP is forbidden in transport tests')
server.requests.post = forbidden_network
def fixture_api(product_id, params):
    record = {'fixtureProduct': product_id, 'fixtureParams': params}
    return {'dataTotal': 1, 'dataList': [record]}
server.call_api = fixture_api
raise SystemExit(server.main([sys.argv[2]]))
"""
PRODUCTS = {
    "transport_coastal_bulk_freight_index": "6a704e0d61c110074d34228f",
    "transport_export_container_freight_index": "6a705029c125d8e5a37c2956",
    "transport_highway_waterway_statistics": "6a705750c125d8e5a37c2993",
    "transport_railway_statistics": "6a705b6961c110074d34242f",
    "transport_civil_aviation_statistics": "6a705c7261c110074d3424a2",
    "transport_postal_statistics": "6a705ee4c125d8e5a37c2a70",
    "transport_urban_passenger_statistics": "6a70603cc125d8e5a37c2a93",
    "transport_port_statistics": "6a706148c125d8e5a37c2b18",
    "transport_investment_statistics": "6a70617f61c110074d342595",
}
REGIONAL_TOOLS = {
    "transport_highway_waterway_statistics",
    "transport_urban_passenger_statistics",
    "transport_port_statistics",
    "transport_investment_statistics",
}


def _env(port: int = 8000) -> dict[str, str]:
    return dict(
        os.environ,
        INTEGRATOR_ID="",
        SECRET_ID="",
        SECRET_KEY="",
        FASTMCP_HOST="127.0.0.1",
        FASTMCP_PORT=str(port),
    )


class TransportTests(IsolatedAsyncioTestCase):
    async def _exercise(self, read, write) -> None:
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            self.assertEqual(initialized.serverInfo.name, "交通大数据")
            listed = await session.list_tools()
            self.assertEqual({tool.name for tool in listed.tools}, set(PRODUCTS))
            for name, product_id in PRODUCTS.items():
                with self.subTest(tool=name):
                    args: dict[str, Any] = {"statTime": "2026-04"}
                    if name in REGIONAL_TOOLS:
                        args["regionType"] = "country"
                    response = await session.call_tool(name, args)
                    self.assertFalse(response.isError)
                    data = response.structuredContent
                    self.assertIsInstance(data, dict)
                    assert data is not None
                    self.assertEqual(data["total"], 1)
                    record = data["resultList"][0]
                    self.assertEqual(record["fixtureProduct"], product_id)
                    self.assertEqual(record["fixtureParams"], args)

            invalid = await session.call_tool(
                "transport_coastal_bulk_freight_index", {"statTime": "2026-13"}
            )
            self.assertTrue(invalid.isError)
            missing_stat_time = await session.call_tool(
                "transport_railway_statistics", {}
            )
            self.assertTrue(missing_stat_time.isError)
            invalid_region = await session.call_tool(
                "transport_port_statistics", {"statTime": "2026-04", "regionType": "city"}
            )
            self.assertTrue(invalid_region.isError)

    async def test_stdio_roundtrip(self) -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", BOOTSTRAP, str(ROOT / "server/mcp_server.py"), "stdio"],
            env=_env(),
            cwd=str(ROOT),
        )
        with open(os.devnull, "w") as log:
            async with stdio_client(params, errlog=log) as (read, write):
                await self._exercise(read, write)

    async def _http_roundtrip(self, transport: str) -> None:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            BOOTSTRAP,
            str(ROOT / "server/mcp_server.py"),
            transport,
            cwd=str(ROOT),
            env=_env(port),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = asyncio.get_running_loop().time() + 15
            while True:
                if process.returncode is not None:
                    self.fail(f"Fixture server exited before startup: {process.returncode}")
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    if asyncio.get_running_loop().time() >= deadline:
                        self.fail("Fixture server startup timed out")
                    await asyncio.sleep(0.05)
            if transport == "sse":
                async with sse_client(f"http://127.0.0.1:{port}/sse", timeout=10) as (read, write):
                    await self._exercise(read, write)
            else:
                async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp", timeout=10) as (
                    read,
                    write,
                    _,
                ):
                    await self._exercise(read, write)
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

    async def test_streamable_http_roundtrip(self) -> None:
        await self._http_roundtrip("streamable-http")

    async def test_sse_roundtrip(self) -> None:
        await self._http_roundtrip("sse")


class LiveTestSafetyTests(TestCase):
    def test_live_smoke_requires_explicit_opt_in(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tests/live_api_smoke.py")],
            capture_output=True,
            text=True,
            timeout=10,
            env=_env(),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--live", result.stderr)

    def test_live_smoke_checks_credentials_before_launch(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tests/live_api_smoke.py"), "--live"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_env(),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("INTEGRATOR_ID 未配置", result.stderr)
