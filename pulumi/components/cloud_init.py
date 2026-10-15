"""
Renders the first-boot cloud-init files for the server node and the agent node.
"""

import json
import string
from dataclasses import dataclass
from pathlib import Path
from typing import List

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


class _Template(string.Template):
    """Recognizes only `@{name}`. A missing value raises `KeyError`."""

    delimiter = "@"
    pattern = r"""
        @(?:
            (?P<escaped>(?!)) |
            (?P<named>(?!)) |
            \{(?P<braced>[a-z][a-z0-9_]*)\} |
            (?P<invalid>(?!))
        )
    """


@dataclass(frozen=True)
class NodeParams:
    """Values for the node. The server node does not use `server_url`."""

    token: str
    k3s_version: str
    node_ip: str
    public_ip: str
    server_url: str
    api_name: str
    disable: List[str]
    swap_gb: int
    kubelet_args: List[str]


def _render(template_name: str, params: NodeParams) -> str:
    template = _Template((TEMPLATE_DIR / template_name).read_text())
    # JSON lists are valid YAML flow sequences.
    return template.substitute(
        token=params.token,
        k3s_version=params.k3s_version,
        node_ip=params.node_ip,
        public_ip=params.public_ip,
        server_url=params.server_url,
        api_name=params.api_name,
        disable=json.dumps(params.disable),
        swap_gb=params.swap_gb,
        kubelet_args=json.dumps(params.kubelet_args),
    )


def render_server(params: NodeParams) -> str:
    """cloud-init for the server node."""
    return _render("server.yaml", params)


def render_agent(params: NodeParams) -> str:
    """cloud-init for the agent node."""
    return _render("agent.yaml", params)
