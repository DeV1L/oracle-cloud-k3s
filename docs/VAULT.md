# Vault

The vault `k3s-vault` holds two secrets like k3s join token and the kubeconfig. The nodes do not read the vault. It's just for convenience. 

## Settings

| Resource | Setting | Meaning |
|----------|---------|---------|
| Vault `k3s-vault` | Type `DEFAULT` | The vault uses a partition of a hardware security module (HSM) that it shares with other tenancies. |
| Key `k3s-key` | AES, 256 bits | A symmetric key. It encrypts the content of the secrets. |
| Key `k3s-key` | Protection mode `SOFTWARE` | OCI keeps the key in software on its servers, not in the HSM. |
| Secrets | Content type `BASE64` | The secret content goes in and comes out in Base64. |

## Secrets

| Secret | Content | Written by |
|--------|---------|------------|
| `k3s-join-token` | The join token: 64 random letters and digits | Pulumi |
| `k3s-kubeconfig` | The kubeconfig of the cluster | Pulumi writes the placeholder `pending`. The owner writes the real kubeconfig. |

## How Pulumi creates the secrets

1. Pulumi creates the vault and the random join token (`RandomPassword`) at the same time. The token is a secret value in the Pulumi state.
2. Pulumi creates the key through the management endpoint of the vault.
3. Pulumi creates both secrets with the key. The content is Base64.
4. The owner copies the kubeconfig from the server node and stores it as a new version of `k3s-kubeconfig`.

Pulumi ignores changes to the content of `k3s-kubeconfig`. Therefore `pulumi up` does not overwrite the kubeconfig of the owner.

The nodes get the join token through the cloud-init, not from the vault.

## Deletion

OCI does not delete a vault immediately. A deleted vault waits 7 to 30 days for its deletion. During this time it can count against the limit of 1 free vault. To rebuild the cluster, keep the vault. Read "Rebuild the cluster and keep the vault" in the [operations guide](OPERATIONS.md).

The commands to read and update the secrets are in the [operations guide](OPERATIONS.md).
