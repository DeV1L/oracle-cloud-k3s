"""
Entry point of the cluster: the reserved public IP and a network load balancer.

The network load balancer works on layer 4 (TCP). An Always Free tenancy has one
network load balancer and one reserved public IP.
"""

from typing import List, Optional

import pulumi
import pulumi_oci as oci

from .config import ProjectConfig


class LoadBalancerComponent(pulumi.ComponentResource):
    """Reserved public IP, network load balancer, and a listener for each port."""

    def __init__(
        self,
        name: str,
        config: ProjectConfig,
        subnet_id: pulumi.Output[str],
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__("oracle-cloud-k3s:loadbalancer:LoadBalancerComponent", name, None, opts)

        self._name = name
        child = pulumi.ResourceOptions(parent=self)

        self.public_ip = oci.core.PublicIp(
            f"{name}-ip",
            compartment_id=config.compartment_ocid,
            lifetime="RESERVED",
            display_name=config.name("lb-ip"),
            freeform_tags=config.tags,
            opts=child,
        )

        self.nlb = oci.networkloadbalancer.NetworkLoadBalancer(
            f"{name}-nlb",
            compartment_id=config.compartment_ocid,
            display_name=config.name("nlb"),
            subnet_id=subnet_id,
            is_private=False,
            reserved_ips=[oci.networkloadbalancer.NetworkLoadBalancerReservedIpArgs(id=self.public_ip.id)],
            freeform_tags=config.tags,
            opts=child,
        )

        # The backends are the fixed private IPs of the nodes.
        node_ips = [config.server_private_ip, config.agent_private_ip]
        self._forward("api", config.API_PORT, [config.server_private_ip])
        self._forward("http", 80, node_ips)
        self._forward("https", 443, node_ips)

        self.ip_address = self.public_ip.ip_address
        api_server_url = self.ip_address.apply(lambda ip: f"https://{ip}:{config.API_PORT}")

        self.register_outputs({"public_ip": self.ip_address, "api_server_url": api_server_url})
        pulumi.export("public_ip", self.ip_address)
        pulumi.export("api_server_url", api_server_url)

    def _forward(self, name: str, port: int, backend_ips: List[str]) -> None:
        """Forward TCP `port` to the same port on the backends."""
        child = pulumi.ResourceOptions(parent=self)
        # The backends see the private IP of the load balancer as the source.
        # The security list checks the client IP when the packet enters the
        # load balancer.
        backend_set = oci.networkloadbalancer.BackendSet(
            f"{self._name}-{name}",
            network_load_balancer_id=self.nlb.id,
            name=name,
            policy="FIVE_TUPLE",
            is_preserve_source=False,
            health_checker=oci.networkloadbalancer.BackendSetHealthCheckerArgs(protocol="TCP", port=port),
            opts=child,
        )
        for ip in backend_ips:
            oci.networkloadbalancer.Backend(
                f"{self._name}-{name}-{ip}",
                network_load_balancer_id=self.nlb.id,
                backend_set_name=backend_set.name,
                ip_address=ip,
                port=port,
                opts=child,
            )
        oci.networkloadbalancer.Listener(
            f"{self._name}-{name}",
            network_load_balancer_id=self.nlb.id,
            name=name,
            default_backend_set_name=backend_set.name,
            port=port,
            protocol="TCP",
            opts=child,
        )
