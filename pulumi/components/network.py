"""
Network for the cluster: one VCN with one public regional subnet.

The security list is stateful and is the only firewall. The cloud-init
removes the reject rules of the host firewall (iptables) in the Ubuntu image.
"""

import re
from typing import Optional

import pulumi
import pulumi_oci as oci

from .config import ProjectConfig


class NetworkComponent(pulumi.ComponentResource):
    """VCN, internet gateway, route table, security list and subnet."""

    DEFAULT_SUBNET_DNS_LABEL = "nodes"
    ANYWHERE = "0.0.0.0/0"
    PROTOCOL_ALL = "all"
    PROTOCOL_ICMP = "1"
    PROTOCOL_TCP = "6"

    def __init__(self, name: str, config: ProjectConfig, opts: Optional[pulumi.ResourceOptions] = None):
        super().__init__("oracle-cloud-k3s:network:NetworkComponent", name, None, opts)

        # The parent groups the resources under this component in the state and
        # in the preview. It is part of the URN of each child: the ID with which
        # Pulumi matches a resource in the code to the resource in the state.
        # The children also get options such as `provider` and `protect` from
        # `opts` of the component.
        child = pulumi.ResourceOptions(parent=self)
        compartment_id = config.compartment_ocid

        # A DNS label gives the nodes resolvable hostnames inside the VCN.
        # OCI allows only letters and digits, at most 15 characters.
        vcn_dns_label = re.sub(r"[^a-z0-9]", "", config.name_prefix.lower())[:15]

        self.vcn = oci.core.Vcn(
            f"{name}-vcn",
            compartment_id=compartment_id,
            cidr_blocks=[config.vcn_cidr],
            display_name=config.name("vcn"),
            dns_label=vcn_dns_label,
            freeform_tags=config.tags,
            opts=child,
        )

        self.internet_gateway = oci.core.InternetGateway(
            f"{name}-igw",
            compartment_id=compartment_id,
            vcn_id=self.vcn.id,
            display_name=config.name("igw"),
            enabled=True,
            freeform_tags=config.tags,
            opts=child,
        )

        self.route_table = oci.core.RouteTable(
            f"{name}-rt",
            compartment_id=compartment_id,
            vcn_id=self.vcn.id,
            display_name=config.name("rt"),
            route_rules=[
                oci.core.RouteTableRouteRuleArgs(
                    destination=self.ANYWHERE,
                    destination_type="CIDR_BLOCK",
                    network_entity_id=self.internet_gateway.id,
                )
            ],
            freeform_tags=config.tags,
            opts=child,
        )

        self.security_list = oci.core.SecurityList(
            f"{name}-sl",
            compartment_id=compartment_id,
            vcn_id=self.vcn.id,
            display_name=config.name("sl"),
            egress_security_rules=[
                oci.core.SecurityListEgressSecurityRuleArgs(
                    destination=self.ANYWHERE,
                    protocol=self.PROTOCOL_ALL,
                )
            ],
            ingress_security_rules=[
                self._tcp_rule(config.admin_cidr, 22, "SSH"),
                self._tcp_rule(config.admin_cidr, 6443, "Kubernetes API"),
                self._tcp_rule(self.ANYWHERE, 80, "HTTP"),
                self._tcp_rule(self.ANYWHERE, 443, "HTTPS"),
                oci.core.SecurityListIngressSecurityRuleArgs(
                    source=config.vcn_cidr,
                    protocol=self.PROTOCOL_ALL,
                    description="All traffic inside the VCN",
                ),
                # Same as the OCI default security list: path MTU discovery.
                # The default rule for ICMP type 3 from the VCN is covered by the rule above.
                oci.core.SecurityListIngressSecurityRuleArgs(
                    source=self.ANYWHERE,
                    protocol=self.PROTOCOL_ICMP,
                    icmp_options=oci.core.SecurityListIngressSecurityRuleIcmpOptionsArgs(type=3, code=4),
                    description="ICMP fragmentation needed",
                ),
            ],
            freeform_tags=config.tags,
            opts=child,
        )

        self.subnet = oci.core.Subnet(
            f"{name}-subnet",
            compartment_id=compartment_id,
            vcn_id=self.vcn.id,
            cidr_block=config.subnet_cidr,
            display_name=config.name("subnet"),
            dns_label=self.DEFAULT_SUBNET_DNS_LABEL,
            prohibit_public_ip_on_vnic=False,
            route_table_id=self.route_table.id,
            security_list_ids=[self.security_list.id],
            freeform_tags=config.tags,
            opts=child,
        )

        self.vcn_id = self.vcn.id
        self.subnet_id = self.subnet.id

        self.register_outputs({"vcn_id": self.vcn_id, "subnet_id": self.subnet_id})
        pulumi.export("vcn_id", self.vcn_id)
        pulumi.export("subnet_id", self.subnet_id)

    def _tcp_rule(self, source: str, port: int, description: str) -> oci.core.SecurityListIngressSecurityRuleArgs:
        return oci.core.SecurityListIngressSecurityRuleArgs(
            source=source,
            protocol=self.PROTOCOL_TCP,
            tcp_options=oci.core.SecurityListIngressSecurityRuleTcpOptionsArgs(min=port, max=port),
            description=description,
        )
