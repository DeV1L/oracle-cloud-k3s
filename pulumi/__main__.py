"""
oracle-cloud-k3s - entry point.

Builds a two-node k3s cluster on OCI Always Free resources. There is one
stack (`default`); every account-specific value is in `Pulumi.default.yaml`.
"""

import pulumi
import pulumi_random as random

from components.cluster import K3sClusterComponent
from components.config import load_config
from components.network import NetworkComponent
from components.vault import VaultComponent

config = load_config()

# Never regenerate the token on a live cluster or new nodes couldn't join.
join_token = random.RandomPassword(
    "k3s-token",
    length=64,
    special=False,
)

network = NetworkComponent("network", config)
vault = VaultComponent("vault", config, join_token=join_token.result)
cluster = K3sClusterComponent("cluster", config, subnet_id=network.subnet_id, join_token=join_token.result)

pulumi.export("k3s_version", config.k3s_version)
pulumi.export("server_private_ip", config.server_private_ip)
