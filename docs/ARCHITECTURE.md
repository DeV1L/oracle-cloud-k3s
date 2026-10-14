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
