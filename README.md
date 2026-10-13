# oracle-cloud-k3s

A Pulumi (Python) project that creates a small k3s cluster on Oracle Cloud Infrastructure (OCI). All resources are inside the [OCI Always Free limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) (the cluster costs nothing).

## What it creates

- One virtual cloud network (VCN) with a public subnet, an internet gateway and a security list.
- Two `VM.Standard.E2.1.Micro` instances with Ubuntu 24.04: one k3s server node and one k3s agent node.
- A reserved public IP for the server node and an ephemeral public IP for the agent node.
- One OCI Vault with two secrets: the k3s join token and the kubeconfig.
- k3s, installed by cloud-init at the first boot, with a pinned version.

The Pulumi state is in an OCI Object Storage bucket. A GitHub Actions workflow runs `pulumi preview` and, on request, `pulumi up`.

## Repository structure

| Path | Content |
|------|---------|
| `pulumi/` | The Pulumi program and the stack configuration |
| `scripts/` | Helper scripts |
| `docs/` | Documentation |
| `.github/workflows/` | The GitHub Actions workflow |
| `AGENTS.md` | Rules for AI agents |

## Requirements

- Python 3.10 or newer
- Pulumi CLI 3.268 or newer (older versions cannot log in to the OCI state bucket)
- The [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm)
- An OCI account. A [Free Tier]((https://signup.cloud.oracle.com/)) is enough.
- `kubectl` and an SSH client

## Quick start

The full procedure, with every command, is in [docs/SETUP.md](docs/SETUP.md). The steps in short:

1. Create an OCI API signing key and a Customer Secret Key.
2. Create the state bucket with `scripts/bootstrap-state-bucket.sh`.
3. Log in to the Pulumi backend and select the stack `default`.
4. Edit `pulumi/Pulumi.default.yaml` for the OCI account.
5. Check the capacity with `scripts/check-capacity.sh`.
6. Run `pulumi up`.
7. Copy the kubeconfig from the server node over SSH. Store it in Vault. Other computers read it from Vault.

The Pulumi state is in a private OCI Object Storage bucket with versioning. Pulumi encrypts the secret values in the state with a key derived from the passphrase (`PULUMI_CONFIG_PASSPHRASE`).

## Documentation

- [Setup guide](docs/SETUP.md)
- [Operations guide](docs/OPERATIONS.md)
