"""
OCI Vault for the cluster secrets: the k3s join token and the kubeconfig.
"""

import base64
from typing import Optional

import pulumi
import pulumi_oci as oci

from .config import ProjectConfig


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


class VaultComponent(pulumi.ComponentResource):
    """Vault, encryption key and the two secrets `join-token` and `kubeconfig`."""

    VAULT_TYPE = "DEFAULT"
    PROTECTION_MODE = "SOFTWARE"
    DEFAULT_KEY_ALGORITHM = "AES"
    DEFAULT_KEY_LENGTH_BYTES = 32
    # A secret must have content when it is created. After the first
    # deployment, the owner stores the real kubeconfig as a new secret version
    # (docs/SETUP.md).
    KUBECONFIG_PLACEHOLDER = "pending"

    def __init__(
        self,
        name: str,
        config: ProjectConfig,
        join_token: pulumi.Output[str],
        opts: Optional[pulumi.ResourceOptions] = None,
    ):
        super().__init__("oracle-cloud-k3s:vault:VaultComponent", name, None, opts)

        # The parent groups the resources under this component in the state and
        # in the preview. It is part of the URN of each child: the ID with which
        # Pulumi matches a resource in the code to the resource in the state.
        # The children also get options such as `provider` and `protect` from
        # `opts` of the component.
        child = pulumi.ResourceOptions(parent=self)
        compartment_id = config.compartment_ocid

        self.vault = oci.kms.Vault(
            f"{name}-vault",
            compartment_id=compartment_id,
            display_name=config.name("vault"),
            vault_type=self.VAULT_TYPE,
            freeform_tags=config.tags,
            opts=child,
        )

        self.key = oci.kms.Key(
            f"{name}-key",
            compartment_id=compartment_id,
            display_name=config.name("key"),
            management_endpoint=self.vault.management_endpoint,
            protection_mode=self.PROTECTION_MODE,
            key_shape=oci.kms.KeyKeyShapeArgs(
                algorithm=self.DEFAULT_KEY_ALGORITHM,
                length=self.DEFAULT_KEY_LENGTH_BYTES,
            ),
            freeform_tags=config.tags,
            opts=child,
        )

        self.join_token_secret = oci.vault.Secret(
            f"{name}-join-token",
            compartment_id=compartment_id,
            vault_id=self.vault.id,
            key_id=self.key.id,
            secret_name=config.name("join-token"),
            description="k3s join token for the cluster nodes",
            secret_content=oci.vault.SecretSecretContentArgs(
                content_type="BASE64",
                content=pulumi.Output.secret(join_token).apply(_b64),
            ),
            freeform_tags=config.tags,
            opts=child,
        )

        self.kubeconfig_secret = oci.vault.Secret(
            f"{name}-kubeconfig",
            compartment_id=compartment_id,
            vault_id=self.vault.id,
            key_id=self.key.id,
            secret_name=config.name("kubeconfig"),
            description="kubeconfig of the cluster",
            secret_content=oci.vault.SecretSecretContentArgs(
                content_type="BASE64",
                content=_b64(self.KUBECONFIG_PLACEHOLDER),
            ),
            freeform_tags=config.tags,
            # The owner manages the content after the first version.
            opts=pulumi.ResourceOptions(parent=self, ignore_changes=["secretContent"]),
        )

        self.register_outputs(
            {
                "vault_ocid": self.vault.id,
                "kubeconfig_secret_ocid": self.kubeconfig_secret.id,
                "join_token_secret_ocid": self.join_token_secret.id,
            }
        )
        pulumi.export("vault_ocid", self.vault.id)
        pulumi.export("kubeconfig_secret_ocid", self.kubeconfig_secret.id)
        pulumi.export("join_token_secret_ocid", self.join_token_secret.id)
