# Network

This document describes the addresses, the routing, the DNS and the firewalls of the cluster. It uses the default values of the stack configuration.

## Addresses

| Network | Range | Set by |
|---------|-------|--------|
| VCN `k3s-vcn` | `10.0.0.0/16` | `vcn_cidr` |
| Subnet `k3s-subnet` | `10.0.1.0/24` | `subnet_cidr` |
| Server node, agent node | `10.0.1.10`, `10.0.1.11` | `server_private_ip`, `agent_private_ips` |
| Pod network | `10.42.0.0/16`, one `/24` for each node | k3s default |
| Service network | `10.43.0.0/16`. The cluster DNS is `10.43.0.10`. | k3s default |

## Routing

- The route table `k3s-rt` sends `0.0.0.0/0` to the internet gateway `k3s-igw`. Traffic inside the VCN uses the local route of the VCN.
- The network interface of a node has only the private IP. The internet gateway translates between the public IP and the private IP. Therefore the server node asks `ifconfig.me` for its public IP.
- Each node goes to the internet through its own public IP. A NAT gateway is not free, so the agent node has an ephemeral public IP.
- Pod traffic between the nodes uses flannel with VXLAN (UDP port 8472) between the private IPs. Pod traffic to the internet leaves with the IP of the node (masquerade).

## DNS

A DNS query from a pod goes through three resolvers:

1. CoreDNS at `10.43.0.10` answers the cluster names (`*.cluster.local`). It forwards all other names to the resolver of the node.
2. The node uses systemd-resolved. k3s gives CoreDNS the upstream server of systemd-resolved, because a pod cannot use the local stub `127.0.0.53`.
3. The OCI VCN resolver at `169.254.169.254` answers internet names and VCN names.

The VCN resolver knows the node names, for example `k3s-agent-1.nodes.k3s.oraclevcn.com`. The DNS labels are `k3s` (the name prefix) for the VCN and `nodes` for the subnet.

## Firewall

Two firewalls filter the traffic. A packet must pass both:

1. The security list `k3s-sl` on the subnet, in OCI.
2. iptables on each node. The Ubuntu image rejects all inbound and forwarded traffic, except SSH, ICMP and replies. The cloud-init inserts accept rules before the reject rules.

Both firewalls are stateful: replies to allowed traffic pass.

| Traffic | Security list | iptables on the node |
|---------|---------------|----------------------|
| SSH, TCP 22 | From `admin_cidr` | Rule of the Ubuntu image |
| Kubernetes API, TCP 6443 | From `admin_cidr` | Accept on the server node |
| HTTP and HTTPS, TCP 80 and 443 | From anywhere | Accept on all nodes |
| All traffic inside the VCN: join, kubelet, VXLAN | From `10.0.0.0/16` | Accept from `10.0.0.0/16` |
| Pod traffic | Not applicable: VXLAN packets use the node IPs | Accept from `10.42.0.0/16`, forward from and to `10.42.0.0/16` |
| ICMP "fragmentation needed" (type 3, code 4) | From anywhere | Rule of the Ubuntu image |
| Outbound traffic | All allowed | All allowed |

The default of `admin_cidr` is `0.0.0.0/0`. Then only the SSH key and the client certificate in the kubeconfig protect the nodes.

k3s adds its own iptables chains (`KUBE-*`) for services and network policies. The cloud-init rules do not change them.

## Workload traffic

traefik is disabled, so the cluster has no ingress controller after the first boot. A `LoadBalancer` service gets no OCI load balancer. The k3s service load balancer (servicelb) runs a pod on each node. This pod opens the service port on the node, so the public IP of each node accepts the traffic. Only ports 80 and 443 are open in both firewalls.
