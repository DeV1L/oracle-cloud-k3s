"""
k3s cluster: one server node and the agent nodes, each with a public IP.

CAUTION: OCI rejects a change to `user_data` or `ssh_authorized_keys` on a live
instance, so Pulumi would replace the instance. Free micro capacity is not
guaranteed, and a deleted instance can take days to get back. The instances
are therefore protected and ignore changes to the image and the metadata.
A node replacement is a deliberate step (`pulumi up --replace`).
"""

import base64
from typing import List, Tuple

import pulumi
import pulumi_oci as oci

from .cloud_init import NodeParams, render_agent, render_server
from .config import K3sConfig


class K3sClusterComponent(pulumi.ComponentResource):
    """Server node, agent nodes and their public IPs."""

    SHAPE = "VM.Standard.E2.1.Micro"
    DEFAULT_IMAGE_OS = "Canonical Ubuntu"
    DEFAULT_IMAGE_OS_VERSION = "24.04"
    SSH_USER = "ubuntu"
    API_PORT = 6443
    # Optional Oracle Cloud Agent plugins use 100 MB of RAM or more.
    # Compute Instance Monitoring stays on, so Oracle sees the node utilization.
    DISABLED_AGENT_PLUGINS = [
        "Management Agent",
        "Cloud Guard Workload Protection",
        "Vulnerability Scanning",
        "OS Management Hub Agent",
        "Custom Logs Monitoring",
    ]

    def __init__(
        self,
        name: str,
        config: K3sConfig,
        subnet_id: pulumi.Output[str],
        join_token: pulumi.Output[str],
        opts: pulumi.ResourceOptions = None,
    ):
        super().__init__("oracle-cloud-k3s:cluster:K3sClusterComponent", name, None, opts)

        self._name = name
        self._config = config
        self._subnet_id = subnet_id
        self._image_id = config.image_ocid or self._latest_image_id()

        server_url = f"https://{config.server_private_ip}:{self.API_PORT}"

        def params(node_ip: str, token: str) -> NodeParams:
            return NodeParams(
                token=token,
                k3s_version=config.k3s_version,
                node_ip=node_ip,
                server_url=server_url,
                vcn_cidr=config.vcn_cidr,
                api_name=config.api_name,
                disable=config.disable,
                swap_gb=config.swap_gb,
            )

        self.server, self.server_public_ip = self._node(
            "server",
            config.server_private_ip,
            join_token.apply(lambda t: render_server(params(config.server_private_ip, t))),
            ip_lifetime="RESERVED",
        )

        self.agents: List[oci.core.Instance] = []
        self.agent_public_ips: List[oci.core.PublicIp] = []
        for index, agent_ip in enumerate(config.agent_private_ips, start=1):
            agent, agent_public_ip = self._node(
                f"agent-{index}",
                agent_ip,
                join_token.apply(lambda t, ip=agent_ip: render_agent(params(ip, t))),
                ip_lifetime="EPHEMERAL",
            )
            self.agents.append(agent)
            self.agent_public_ips.append(agent_public_ip)

        server_ip = self.server_public_ip.ip_address
        agent_ips = pulumi.Output.all(*[ip.ip_address for ip in self.agent_public_ips])
        api_server_url = server_ip.apply(lambda ip: f"https://{ip}:{self.API_PORT}")

        self.register_outputs(
            {
                "server_public_ip": server_ip,
                "agent_public_ips": agent_ips,
                "api_server_url": api_server_url,
            }
        )
        pulumi.export("server_public_ip", server_ip)
        pulumi.export("agent_public_ips", agent_ips)
        pulumi.export("api_server_url", api_server_url)
        pulumi.export("ssh_user", self.SSH_USER)

    def _latest_image_id(self) -> pulumi.Output[str]:
        images = oci.core.get_images_output(
            compartment_id=self._config.compartment_ocid,
            operating_system=self.DEFAULT_IMAGE_OS,
            operating_system_version=self.DEFAULT_IMAGE_OS_VERSION,
            shape=self.SHAPE,
            sort_by="TIMECREATED",
            sort_order="DESC",
        )
        return images.images[0].id

    def _node(
        self,
        role: str,
        private_ip: str,
        cloud_init: pulumi.Output[str],
        ip_lifetime: str,
    ) -> Tuple[oci.core.Instance, oci.core.PublicIp]:
        config = self._config
        display_name = config.name(role)

        # The subnet uses the route table to the internet gateway. Through the
        # subnet ID the instance waits for both, so the first boot has internet.
        instance = oci.core.Instance(
            f"{self._name}-{role}",
            compartment_id=config.compartment_ocid,
            availability_domain=config.availability_domain,
            shape=self.SHAPE,
            display_name=display_name,
            create_vnic_details=oci.core.InstanceCreateVnicDetailsArgs(
                subnet_id=self._subnet_id,
                assign_public_ip="false",
                private_ip=private_ip,
                hostname_label=display_name,
                display_name=display_name,
                freeform_tags=config.tags,
            ),
            source_details=oci.core.InstanceSourceDetailsArgs(
                source_type="image",
                source_id=self._image_id,
            ),
            metadata={
                "ssh_authorized_keys": "\n".join(config.ssh_public_keys),
                "user_data": pulumi.Output.secret(cloud_init).apply(
                    lambda text: base64.b64encode(text.encode()).decode()
                ),
            },
            agent_config=oci.core.InstanceAgentConfigArgs(
                is_monitoring_disabled=False,
                plugins_configs=[
                    oci.core.InstanceAgentConfigPluginsConfigArgs(name=plugin, desired_state="DISABLED")
                    for plugin in self.DISABLED_AGENT_PLUGINS
                ],
            ),
            preserve_boot_volume=False,
            freeform_tags=config.tags,
            # The fixed private IP and the micro quota allow no second instance,
            # so a replacement deletes the old instance first.
            opts=pulumi.ResourceOptions(
                parent=self,
                protect=True,
                ignore_changes=["sourceDetails", "metadata"],
                delete_before_replace=True,
            ),
        )

        # The public IP attaches to the primary private IP of the VNIC. Its ID
        # is known only after the instance exists. An Always Free tenancy has
        # one reserved public IP: the server node gets it, so the API address
        # survives a node replacement. Agent nodes get an ephemeral public IP,
        # which they need for internet access (there is no free NAT gateway).
        private_ip_id = pulumi.Output.all(instance.id, self._subnet_id).apply(
            lambda args: oci.core.get_private_ips(ip_address=private_ip, subnet_id=args[1]).private_ips[0].id
        )
        ip_opts = pulumi.ResourceOptions(parent=self)
        if ip_lifetime == "EPHEMERAL":
            # OCI deletes an ephemeral IP with its VNIC and cannot move it to
            # another private IP: a new instance needs a new ephemeral IP.
            ip_opts = pulumi.ResourceOptions(parent=self, replace_on_changes=["privateIpId"], delete_before_replace=True)
        public_ip = oci.core.PublicIp(
            f"{self._name}-{role}-ip",
            compartment_id=config.compartment_ocid,
            lifetime=ip_lifetime,
            private_ip_id=private_ip_id,
            display_name=config.name(f"{role}-ip"),
            freeform_tags=config.tags,
            opts=ip_opts,
        )
        return instance, public_ip
