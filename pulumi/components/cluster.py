"""
k3s cluster: one server node and one agent node, each with an ephemeral public IP.

CAUTION: OCI rejects a change to `user_data` or `ssh_authorized_keys` on a live
instance, so Pulumi would replace the instance. Free micro capacity is not
guaranteed. The instances are protected and ignore changes to the image and the 
metadata. A node replacement is a manual step (`pulumi up --replace`).
"""

import base64
from typing import Callable, List, Optional

import pulumi
import pulumi_oci as oci

from .cloud_init import NodeParams, render_agent, render_server
from .config import ProjectConfig


class K3sClusterComponent(pulumi.ComponentResource):
    """Server node and agent node."""

    def __init__(
        self,
        name: str,
        config: ProjectConfig,
        subnet_id: pulumi.Output[str],
        join_token: pulumi.Output[str],
        public_ip: pulumi.Output[str],
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__("oracle-cloud-k3s:cluster:K3sClusterComponent", name, None, opts)

        self._name = name
        self._config = config
        self._subnet_id = subnet_id
        self._image_id = config.image_ocid or self._latest_image_id()

        def cloud_init(render: Callable[[NodeParams], str], node_ip: str) -> pulumi.Output[str]:
            """The cloud-init of one node. All nodes get the same join token."""

            def with_values(values: List[str]) -> str:
                token, cluster_ip = values
                return render(
                    NodeParams(
                        token=token,
                        k3s_version=config.k3s_version,
                        node_ip=node_ip,
                        server_url=config.server_url,
                        api_host=config.api_host(cluster_ip),
                        # Names in the API certificate. The DNS name is optional.
                        tls_san=[node_ip, cluster_ip] + ([config.api_name] if config.api_name else []),
                        kubeconfig_name=config.KUBECONFIG_NAME,
                        disable=config.disable,
                        swap_gb=config.swap_gb,
                        kubelet_args=config.KUBELET_ARGS,
                    )
                )

            # The token and the public IP exist only after Pulumi creates them.
            # `apply` calls `with_values` with both values then.
            return pulumi.Output.all(join_token, public_ip).apply(with_values)

        self.server = self._instance(
            "server",
            config.server_private_ip,
            cloud_init(render_server, config.server_private_ip),
        )
        self.agent = self._instance(
            "agent-1",
            config.agent_private_ip,
            cloud_init(render_agent, config.agent_private_ip),
        )

        self.register_outputs(
            {
                "server_public_ip": self.server.public_ip,
                "agent_public_ip": self.agent.public_ip,
            }
        )
        pulumi.export("server_public_ip", self.server.public_ip)
        pulumi.export("agent_public_ip", self.agent.public_ip)
        pulumi.export("ssh_user", config.SSH_USER)

    def _latest_image_id(self) -> pulumi.Output[str]:
        images = oci.core.get_images_output(
            compartment_id=self._config.compartment_ocid,
            operating_system=self._config.IMAGE_OS,
            operating_system_version=self._config.IMAGE_OS_VERSION,
            shape=self._config.SHAPE,
            sort_by="TIMECREATED",
            sort_order="DESC",
        )
        return images.images[0].id

    def _instance(self, role: str, private_ip: str, cloud_init: pulumi.Output[str]) -> oci.core.Instance:
        """One node instance with a fixed private IP and an ephemeral public IP."""
        config = self._config
        display_name = config.name(role)

        return oci.core.Instance(
            f"{self._name}-{role}",
            compartment_id=config.compartment_ocid,
            availability_domain=config.availability_domain,
            shape=config.SHAPE,
            display_name=display_name,
            create_vnic_details=oci.core.InstanceCreateVnicDetailsArgs(
                subnet_id=self._subnet_id,
                # The node needs it for internet access: a NAT gateway is not free.
                assign_public_ip="true",
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
                    for plugin in config.DISABLED_AGENT_PLUGINS
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
