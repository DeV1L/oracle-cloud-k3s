"""
k3s cluster: one server node and one agent node, each with a public IP.

CAUTION: OCI rejects a change to `user_data` or `ssh_authorized_keys` on a live
instance, so Pulumi would replace the instance. Free micro capacity is not
guaranteed. The instances are protected and ignore changes to the image and the 
metadata. A node replacement is a manual step (`pulumi up --replace`).
"""

import base64
from typing import Callable, Optional

import pulumi
import pulumi_oci as oci

from .cloud_init import NodeParams, render_agent, render_server
from .config import ProjectConfig


class K3sClusterComponent(pulumi.ComponentResource):
    """Server node, agent node and their public IPs."""

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
        config: ProjectConfig,
        subnet_id: pulumi.Output[str],
        join_token: pulumi.Output[str],
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__("oracle-cloud-k3s:cluster:K3sClusterComponent", name, None, opts)

        self._name = name
        self._config = config
        self._subnet_id = subnet_id
        self._image_id = config.image_ocid or self._latest_image_id()

        server_url = f"https://{config.server_private_ip}:{self.API_PORT}"

        def cloud_init(render: Callable[[NodeParams], str], node_ip: str) -> pulumi.Output[str]:
            """The cloud-init of one node. All nodes get the same join token."""

            def with_token(token: str) -> str:
                return render(
                    NodeParams(
                        token=token,
                        k3s_version=config.k3s_version,
                        node_ip=node_ip,
                        server_url=server_url,
                        api_name=config.api_name,
                        disable=config.disable,
                        swap_gb=config.swap_gb,
                    )
                )

            # The token exists only after Pulumi creates it. `apply` calls `with_token` with the token then.
            return join_token.apply(with_token)

        # Server node: the instance, then its reserved public IP.
        self.server = self._instance(
            "server",
            config.server_private_ip,
            cloud_init(render_server, config.server_private_ip),
        )
        self.server_public_ip = oci.core.PublicIp(
            f"{name}-server-ip",
            compartment_id=config.compartment_ocid,
            lifetime="RESERVED",
            private_ip_id=self._private_ip_id(self.server, config.server_private_ip),
            display_name=config.name("server-ip"),
            freeform_tags=config.tags,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Agent node: the instance, then its ephemeral public IP.
        self.agent = self._instance(
            "agent-1",
            config.agent_private_ip,
            cloud_init(render_agent, config.agent_private_ip),
        )
        self.agent_public_ip = oci.core.PublicIp(
            f"{name}-agent-1-ip",
            compartment_id=config.compartment_ocid,
            lifetime="EPHEMERAL",
            private_ip_id=self._private_ip_id(self.agent, config.agent_private_ip),
            display_name=config.name("agent-1-ip"),
            freeform_tags=config.tags,
            # OCI deletes an ephemeral IP with its VNIC and cannot move it to
            # another private IP: a new instance needs a new ephemeral IP.
            opts=pulumi.ResourceOptions(
                parent=self,
                replace_on_changes=["privateIpId"],
                delete_before_replace=True,
            ),
        )

        server_ip = self.server_public_ip.ip_address
        agent_ip = self.agent_public_ip.ip_address
        api_server_url = server_ip.apply(lambda ip: f"https://{ip}:{self.API_PORT}")

        self.register_outputs(
            {
                "server_public_ip": server_ip,
                "agent_public_ip": agent_ip,
                "api_server_url": api_server_url,
            }
        )
        pulumi.export("server_public_ip", server_ip)
        pulumi.export("agent_public_ip", agent_ip)
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

    def _instance(self, role: str, private_ip: str, cloud_init: pulumi.Output[str]) -> oci.core.Instance:
        """One node instance with a fixed private IP and no public IP."""
        config = self._config
        display_name = config.name(role)

        return oci.core.Instance(
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
                "user_data": cloud_init.apply(lambda text: base64.b64encode(text.encode()).decode()),
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

    def _private_ip_id(self, instance: oci.core.Instance, private_ip: str) -> pulumi.Output[str]:
        """ID of the private IP object of an instance, to attach a public IP to.

        The object exists only after the instance exists: `instance.id` makes
        the lookup wait for it.
        """
        return pulumi.Output.all(instance.id, self._subnet_id).apply(
            lambda args: oci.core.get_private_ips(ip_address=private_ip, subnet_id=args[1]).private_ips[0].id
        )
