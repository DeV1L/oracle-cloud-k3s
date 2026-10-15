# Network

This document describes the addresses, the routing, the DNS and the firewalls of the cluster. It uses the default values of the stack configuration.

## Addresses

| Network | Range | Set by |
|---------|-------|--------|
| VCN `k3s-vcn` | `10.0.0.0/16` | `vcn_cidr` |
| Subnet `k3s-subnet` | `10.0.1.0/24` | `subnet_cidr` |
| Server node, agent node | `10.0.1.10`, `10.0.1.11` | `server_private_ip`, `agent_private_ip` |
| Cluster public IP (reserved, on the load balancer) | Assigned by OCI | Stack output `public_ip` |
| Node public IPs (ephemeral, new after a replacement) | Assigned by OCI | Stack outputs `server_public_ip`, `agent_public_ip` |
| Pod network | `10.42.0.0/16`, one `/24` for each node | k3s default |
| Service network | `10.43.0.0/16`. The cluster DNS is `10.43.0.10`. | k3s default |

## Routing

- The route table `k3s-rt` sends `0.0.0.0/0` to the internet gateway `k3s-igw`. Traffic inside the VCN uses the local route of the VCN.
- The network interface of a node has only the private IP. The internet gateway translates between the ephemeral public IP and the private IP.
- Each node goes to the internet through its own ephemeral public IP. A NAT gateway is not free.
- Pod traffic between the nodes uses flannel with VXLAN (UDP port 8472) between the private IPs. Pod traffic to the internet leaves with the IP of the node (masquerade).

## Load balancer

The network load balancer `k3s-nlb` holds the cluster public IP. It is the entry point of the cluster. It works on layer 4 (TCP).

| Port | Backends | Use |
|------|----------|-----|
| 6443 | Server node | Kubernetes API (kubectl) |
| 80 | Both nodes | HTTP to `LoadBalancer` services |
| 443 | Both nodes | HTTPS to `LoadBalancer` services |

- The backends are the fixed private IPs of the nodes. A node replacement does not change the load balancer.
- The health check opens a TCP connection to the port. A port without a listener on the node is `CRITICAL`, for example 443 until a service uses it.
- The backends see the private IP of the load balancer as the source. The security list checks the client IP when the packet enters the load balancer.

## DNS

A DNS query from a pod goes through three resolvers:

1. CoreDNS at `10.43.0.10` answers the cluster names (`*.cluster.local`). It forwards all other names to the resolver of the node.
2. The node uses systemd-resolved. k3s gives CoreDNS the upstream server of systemd-resolved, because a pod cannot use the local stub `127.0.0.53`.
3. The OCI VCN resolver at `169.254.169.254` answers internet names and VCN names.

The VCN resolver knows the node names, for example `k3s-agent-1.nodes.k3s.oraclevcn.com`. The DNS labels are `k3s` (the name prefix) for the VCN and `nodes` for the subnet.

## Firewall

The security list `k3s-sl` on the subnet is the only firewall. It is stateful: replies to allowed traffic pass.

| Traffic | Allowed from |
|---------|--------------|
| SSH, TCP 22 | `admin_cidr` |
| Kubernetes API, TCP 6443 | `admin_cidr` |
| HTTP and HTTPS, TCP 80 and 443 | Anywhere |
| All traffic inside the VCN: join, kubelet, VXLAN | `10.0.0.0/16` |
| ICMP "fragmentation needed" (type 3, code 4) | Anywhere |

All outbound traffic is allowed.

The default of `admin_cidr` is `0.0.0.0/0`. Then only the SSH key and the client certificate in the kubeconfig protect the nodes.

The Ubuntu image also has an iptables firewall. The cloud-init turns it off, so ports open only in the security list.

k3s adds its own iptables chains (`KUBE-*`, `FLANNEL-*`) for services and the pod network.

## Workload traffic

traefik is disabled, so the cluster has no ingress controller after the first boot. Kubernetes does not create OCI load balancers. The k3s service load balancer (servicelb) runs a pod on each node for each `LoadBalancer` service. This pod opens the service port on the node. The network load balancer forwards ports 80 and 443 to both nodes. Other ports do not reach the cluster.
