"""
Typed stack configuration.

Every component gets its settings from one `ProjectConfig` object. Only this
module reads `pulumi.Config`, so the keys and their defaults are in one place.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import pulumi


@dataclass(frozen=True)
class ProjectConfig:
    """Values of the `k3s` and `oci` configuration namespaces, with defaults applied."""

    DEFAULT_K3S_VERSION = "v1.36.5+k3s1"
    DEFAULT_NAME_PREFIX = "k3s"
    DEFAULT_VCN_CIDR = "10.0.0.0/16"
    DEFAULT_SUBNET_CIDR = "10.0.1.0/24"
    DEFAULT_SERVER_PRIVATE_IP = "10.0.1.10"
    DEFAULT_AGENT_PRIVATE_IP = "10.0.1.11"
    DEFAULT_ADMIN_CIDR = "0.0.0.0/0"
    DEFAULT_API_NAME = "oci-k3s"
    DEFAULT_DISABLE = ["traefik"]
    DEFAULT_SWAP_GB = 2

    # Fixed values, not stack configuration keys. A change can replace an
    # instance or leave the Always Free limits.
    SHAPE = "VM.Standard.E2.1.Micro"
    IMAGE_OS = "Canonical Ubuntu"
    IMAGE_OS_VERSION = "24.04 Minimal"
    SSH_USER = "ubuntu"
    API_PORT = 6443
    # Optional Oracle Cloud Agent plugins use 50 MB of RAM or more.
    # Compute Instance Monitoring stays on, so Oracle sees the node utilization.
    DISABLED_AGENT_PLUGINS = [
        "Management Agent",
        "Cloud Guard Workload Protection",
        "Vulnerability Scanning",
        "OS Management Hub Agent",
        "Custom Logs Monitoring",
    ]
    # 1 GB nodes: keep memory for the OS and k3s, and evict pods before the
    # kernel OOM killer acts.
    KUBELET_ARGS = [
        "system-reserved=memory=128Mi",
        "kube-reserved=memory=128Mi",
        "eviction-hard=memory.available<50Mi",
    ]

    region: str
    compartment_ocid: str
    availability_domain: str
    ssh_public_keys: List[str]
    k3s_version: str
    name_prefix: str
    vcn_cidr: str
    subnet_cidr: str
    server_private_ip: str
    agent_private_ip: str
    admin_cidr: str
    api_name: str
    disable: List[str]
    image_ocid: Optional[str]
    swap_gb: int
    stack: str

    @property
    def tags(self) -> Dict[str, str]:
        """Freeform tags for every resource."""
        return {
            "managed-by": "pulumi",
            "project": "oracle-cloud-k3s",
            "stack": self.stack,
        }

    @property
    def server_url(self) -> str:
        """The URL at which the agent node joins the server node."""
        return f"https://{self.server_private_ip}:{self.API_PORT}"

    def name(self, suffix: str) -> str:
        """Display name with the configured prefix, for example `k3s-vcn`."""
        return f"{self.name_prefix}-{suffix}"


def load_config() -> ProjectConfig:
    """Read the stack configuration. Fails with a clear message when a required key is missing."""
    k3s = pulumi.Config("k3s")
    oci = pulumi.Config("oci")
    # An empty list is a valid value: no disabled component.
    disable = k3s.get_object("disable")
    return ProjectConfig(
        region=oci.require("region"),
        compartment_ocid=k3s.require("compartment_ocid"),
        availability_domain=k3s.require("availability_domain"),
        ssh_public_keys=k3s.require_object("ssh_public_keys"),
        k3s_version=k3s.get("k3s_version") or ProjectConfig.DEFAULT_K3S_VERSION,
        name_prefix=k3s.get("name_prefix") or ProjectConfig.DEFAULT_NAME_PREFIX,
        vcn_cidr=k3s.get("vcn_cidr") or ProjectConfig.DEFAULT_VCN_CIDR,
        subnet_cidr=k3s.get("subnet_cidr") or ProjectConfig.DEFAULT_SUBNET_CIDR,
        server_private_ip=k3s.get("server_private_ip") or ProjectConfig.DEFAULT_SERVER_PRIVATE_IP,
        agent_private_ip=k3s.get("agent_private_ip") or ProjectConfig.DEFAULT_AGENT_PRIVATE_IP,
        admin_cidr=k3s.get("admin_cidr") or ProjectConfig.DEFAULT_ADMIN_CIDR,
        api_name=k3s.get("api_name") or ProjectConfig.DEFAULT_API_NAME,
        disable=ProjectConfig.DEFAULT_DISABLE if disable is None else disable,
        image_ocid=k3s.get("image_ocid"),
        swap_gb=k3s.get_int("swap_gb") or ProjectConfig.DEFAULT_SWAP_GB,
        stack=pulumi.get_stack(),
    )
