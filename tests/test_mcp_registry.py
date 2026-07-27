"""Tool Registry 单元测试。"""
from app.worker.mcp.registry import ToolRegistry, ToolDescriptor
from config.settings import MCPConfig


class _FakeTool:
    def __init__(self, name, description="", input_schema=None):
        self.name = name
        self.description = description
        self.inputSchema = input_schema or {"type": "object", "properties": {}}


def test_register_and_lookup():
    reg = ToolRegistry()
    reg.register(
        ToolDescriptor(
            server_name="fs",
            tool_name="read",
            qualified_name="fs:read",
            description="read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
    )
    assert "fs:read" in reg
    got = reg.get("fs:read")
    assert got is not None
    assert got.server_name == "fs"
    assert got.tool_name == "read"


def test_register_many_from_mcp_tools():
    reg = ToolRegistry()
    tools = [
        _FakeTool("read", "read file"),
        _FakeTool("write", "write file"),
    ]
    n = reg.register_many("fs", tools)
    assert n == 2
    assert reg.get("fs:read") is not None
    assert reg.get("fs:write") is not None
    assert sorted(t.qualified_name for t in reg.all()) == ["fs:read", "fs:write"]


def test_denylist_filters_tools():
    cfg = MCPConfig(denylist=["fs:write"])
    reg = ToolRegistry(cfg)
    reg.register(
        ToolDescriptor("fs", "read", "fs:read", "r", {})
    )
    reg.register(
        ToolDescriptor("fs", "write", "fs:write", "w", {})
    )
    assert "fs:read" in reg
    assert "fs:write" not in reg


def test_allowlist_filters_tools():
    cfg = MCPConfig(allowlist=["fs:read"])
    reg = ToolRegistry(cfg)
    reg.register(ToolDescriptor("fs", "read", "fs:read", "r", {}))
    reg.register(ToolDescriptor("fs", "write", "fs:write", "w", {}))
    assert "fs:read" in reg
    assert "fs:write" not in reg


def test_by_server_groups_correctly():
    reg = ToolRegistry()
    reg.register(ToolDescriptor("fs", "read", "fs:read", "", {}))
    reg.register(ToolDescriptor("web", "search", "web:search", "", {}))
    fs_tools = reg.by_server("fs")
    assert [t.qualified_name for t in fs_tools] == ["fs:read"]


def test_register_many_with_invalid_input_is_skipped():
    reg = ToolRegistry()
    n = reg.register_many("fs", [_FakeTool("read"), "not-a-tool", object()])
    # _FakeTool("read") 正常 + 两个无效
    assert n == 1
    assert "fs:read" in reg
