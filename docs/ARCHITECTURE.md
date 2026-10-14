# Architecture

This document shows the parts of the project and how they connect. The diagrams use the default values of the stack configuration.

## Infrastructure in OCI

All resources are in the root compartment of the tenancy, in the home region. The nodes are in availability domain AD-1.

```mermaid
---
config:
  layout: dagre
---
flowchart TB
    clients["Internet clients"]

    subgraph oci["OCI tenancy: root compartment, home region"]
        subgraph vcn["VCN k3s-vcn 10.0.0.0/16"]
            igw["Internet gateway<br/>k3s-igw"]
            rt["Route table<br/>k3s-rt<br/>0.0.0.0/0 to the internet gateway"]
            sl["Security list<br/>k3s-sl"]
            subgraph subnet["Public subnet k3s-subnet 10.0.1.0/24"]
                server["Server node<br/>k3s-server<br/>10.0.1.10<br/>"]
                agent["Agent node<br/>k3s-agent-1<br/>10.0.1.11<br/>"]
            end
        end
        rip["Reserved public IP<br/>k3s-server-ip"]
        eip["Ephemeral public IP<br/>k3s-agent-1-ip"]
        subgraph vault["Vault k3s-vault, type DEFAULT"]
            tokensecret["Secret<br/>k3s-join-token"]
            kcsecret["Secret<br/>k3s-kubeconfig"]
        end
    end

    clients -- "HTTP 80, HTTPS 443" --> rip
    clients -- "HTTP 80, HTTPS 443" --> eip
    rip --- server
    eip --- agent
    agent -- "join: 10.0.1.10:6443<br/>with the join token" --> server
    subnet -.- rt
    subnet -.- sl
    rt -- "outbound traffic" --> igw
    igw ~~~ tokensecret & kcsecret
```

| Part | Why it is like this |
|------|---------------------|
| Reserved public IP on the server node | The API address stays the same after a replacement of the server node. The tenancy has 1 free reserved public IP. |
| Ephemeral public IP on the agent node | The agent node needs it for internet access. A NAT gateway is not free. |
| Fixed private IPs | The agent nodes find the server node at `https://10.0.1.10:6443`. |

[Network](NETWORK.md) describes the addresses, the routing, the DNS and the firewalls.

## Pulumi program

`__main__.py` reads the configuration once and creates three components and a random join token.

```mermaid
flowchart TB
    yaml["Pulumi.default.yaml"] --> config["config.py<br/>load_config() returns ProjectConfig"]
    config --> main["__main__.py"]

    main --> token["RandomPassword<br/>k3s-token<br/>64 characters"]
    main --> network["NetworkComponent<br/>network.py"]
    main --> vaultc["VaultComponent<br/>vault.py"]
    main --> cluster["K3sClusterComponent<br/>cluster.py"]

    network --> netres["VCN, internet gateway,<br/>route table, security list, subnet"]
    vaultc --> vaultres["Vault, key,<br/>secrets join-token and kubeconfig"]
    cluster --> clusterres["Instances server and agent-1,<br/>public IPs"]

    token -- "join token" --> vaultc
    token -- "join token" --> cluster
    network -- "subnet ID" --> cluster

    cluster --> cloudinit["cloud_init.py"]
    templates["templates/server.yaml<br/>templates/agent.yaml"] --> cloudinit
    cloudinit -- "user_data" --> clusterres
```

| Component | Type token | Stack outputs |
|-----------|------------|---------------|
| `NetworkComponent` | `oracle-cloud-k3s:network:NetworkComponent` | `vcn_id`, `subnet_id` |
| `VaultComponent` | `oracle-cloud-k3s:vault:VaultComponent` | `vault_ocid`, `join_token_secret_ocid`, `kubeconfig_secret_ocid` |
| `K3sClusterComponent` | `oracle-cloud-k3s:cluster:K3sClusterComponent` | `server_public_ip`, `agent_public_ips`, `api_server_url`, `ssh_user` |

### Configuration

The function `load_config()` in `config.py` reads the stack configuration and returns it as one `ProjectConfig` object. `__main__.py` gives this object to each component. The components do not read the stack configuration.

A value is in one of three places:

| Place | Values | Why |
|-------|--------|-----|
| `Pulumi.default.yaml`, required keys | Region, compartment, availability domain, SSH public keys | These values are different for each project. |
| `DEFAULT_*` constants in `config.py` | k3s version, CIDRs, private IPs, name prefix, API name, disabled k3s components, swap size | These defaults work for all. A key in `Pulumi.default.yaml` overrides a default. |
| Constants in the components | Shape, image OS, SSH user, API port, disabled Oracle Cloud Agent plugins | These are not options. A change can replace an instance. |

For `agent_private_ips` and `disable`, an empty list is a valid value. Only a missing key gets the default.

## First boot

cloud-init runs the bootstrap script `/usr/local/sbin/k3s-bootstrap.sh` once, at the first boot. The script is safe to run a second time.

```mermaid
sequenceDiagram
    actor Owner
    participant Pulumi
    participant Server as Server node
    participant Agent as Agent node
    participant Vault

    Owner->>Pulumi: pulumi up
    Pulumi->>Vault: create the secrets join-token and kubeconfig (placeholder)
    Pulumi->>Server: create the instance with user_data
    Pulumi->>Agent: create the instance with user_data
    Note over Server,Agent: cloud-init: swap, iptables
    Server->>Server: find the public IP (ifconfig.me or api.ipify.org)
    Server->>Server: install k3s server, add the public IP to the certificate
    Server->>Server: write /home/ubuntu/kubeconfig.yaml
    Agent->>Server: install k3s agent, join at 10.0.1.10:6443 with the join token
    Owner->>Server: scp kubeconfig.yaml
    Owner->>Vault: store the kubeconfig as a new secret version
    Owner->>Vault: on another computer, read the kubeconfig
```
