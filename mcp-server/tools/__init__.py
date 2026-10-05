"""Read-only MCP diagnostic tools. Importing this package registers every tool in tools.common.REGISTRY."""

from tools import (  # noqa: F401
    device_info,
    dns_check,
    http_check,
    interface_status,
    ping,
    previous_incident,
    search_logs,
    server_status,
    service_status,
    topology_path,
)
from tools.common import REGISTRY, call_tool  # noqa: F401
