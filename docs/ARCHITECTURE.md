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
    owner["Owner"]

    subgraph oci["OCI tenancy: root compartment, home region"]
        lbip["Reserved public IP<br/>k3s-lb-ip"]
        subgraph vcn["VCN k3s-vcn 10.0.0.0/16"]
            igw["Internet gateway<br/>k3s-igw"]
            rt["Route table<br/>k3s-rt<br/>0.0.0.0/0 to the internet gateway"]
            sl["Security list<br/>k3s-sl"]
            subgraph subnet["Public subnet k3s-subnet 10.0.1.0/24"]
                nlb["Network load balancer<br/>k3s-nlb"]
                server["Server node<br/>k3s-server<br/>10.0.1.10<br/>ephemeral public IP"]
                agent["Agent node<br/>k3s-agent-1<br/>10.0.1.11<br/>ephemeral public IP"]
            end
        end
        subgraph vault["Vault k3s-vault, type DEFAULT"]
            tokensecret["Secret<br/>k3s-join-token"]
            kcsecret["Secret<br/>k3s-kubeconfig"]
        end
    end

    clients -- "HTTP 80, HTTPS 443" --> lbip
    owner -- "kubectl 6443" --> lbip
    owner -- "SSH 22" --> server & agent
    lbip --- nlb
    nlb -- "6443" --> server
    nlb -- "80, 443" --> server & agent
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
    Pulumi->>Pulumi: create the reserved public IP and the load balancer
    Pulumi->>Server: create the instance with user_data (with the public IP)
    Pulumi->>Agent: create the instance with user_data
    Note over Server,Agent: cloud-init: swap, iptables
    Server->>Server: install k3s server, with the public IP and the DNS name in the certificate
    Server->>Server: write /home/ubuntu/kubeconfig.yaml
    Agent->>Server: install k3s agent, join at 10.0.1.10:6443 with the join token
    Owner->>Server: scp kubeconfig.yaml
    Owner->>Vault: store the kubeconfig as a new secret version
    Owner->>Vault: on another computer, read the kubeconfig
```
