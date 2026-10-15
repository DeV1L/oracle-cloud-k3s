# oracle-cloud-k3s

A Pulumi (Python) project that creates a small **k3s** cluster on **Oracle Cloud Infrastructure** (OCI). All resources are inside the [OCI Always Free limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) (the cluster costs nothing).

## What it creates

- One virtual cloud network (VCN) with a public subnet, an internet gateway and a security list.
- Two `VM.Standard.E2.1.Micro` instances with Ubuntu 24.04 Minimal: one k3s server node and one k3s agent node.
- A network load balancer with the reserved public IP: the entry point for kubectl, HTTP and HTTPS.
- An ephemeral public IP on each node, for internet access and SSH.
- One OCI Vault with two secrets: the k3s join token and the kubeconfig.
- k3s, installed by cloud-init at the first boot, with a pinned version.
- A GitHub Actions workflow: `pulumi preview` on pull requests and pushes, `pulumi up` on manual start.

The Pulumi state is in an OCI Object Storage bucket.

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
- An OCI account. A [Free Tier](https://signup.cloud.oracle.com/) is enough.
- `kubectl` and an SSH client

## Quick start

The full procedure, with every command, is in [docs/SETUP.md](docs/SETUP.md). The steps in short:

1. Create OCI keys (API signing key and a Customer Secret Key).
2. Create the state bucket.
3. Authenticate Pulumi CLI and select the stack.
4. Save OCI account settings and your SSH public key in `pulumi/Pulumi.default.yaml`.
5. Deploy the cluster by `pulumi up` command.
6. Copy the kubeconfig from the server node over SSH.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Network](docs/NETWORK.md)
- [Vault](docs/VAULT.md)
- [Pulumi program](docs/PULUMI.md)
- [k3s and cloud-init](docs/K3S.md)
- [Setup guide](docs/SETUP.md)
- [Operations guide](docs/OPERATIONS.md)
