# k3s and cloud-init

k3s is a small Kubernetes distribution in one binary. The server node runs the control plane and workloads. The agent node runs workloads only.

The nodes use the image Canonical Ubuntu 24.04 Minimal. It has fewer packages and services than the full image, so more RAM is free.

## Cloud-init

Each instance gets a cloud-init file from `pulumi/templates/` as `user_data`. cloud-init runs it once, at the first boot. The file does two things:

1. It writes the k3s configuration `/etc/rancher/k3s/config.yaml`.
2. It writes the bootstrap script `/usr/local/sbin/k3s-bootstrap.sh` and runs it.

The bootstrap script does these steps:

1. It makes a swap file (`swap_gb`, 2 GB by default).
2. It removes the reject rules of the iptables firewall in the Ubuntu image.
3. It turns off services that a node does not need, for example fwupd, multipathd and iscsid. The Minimal image does not have most of them.
4. It installs the pinned k3s version from `get.k3s.io`.
5. Server node only: it writes `/home/ubuntu/kubeconfig.yaml` with the cluster public IP.

The script writes its log to `/var/log/k3s-bootstrap.log`. It is safe to run a second time.

## k3s configuration

| Key | Node | Value |
|-----|------|-------|
| `token` | Both | The join token |
| `node-ip` | Both | The private IP of the node |
| `kubelet-arg` | Both | Memory reserved for the OS and k3s, and the eviction limit (`KUBELET_ARGS`) |
| `tls-san` | Server | Additional names in the API certificate: the private IP, the cluster public IP of the load balancer and the DNS name `api_name`, when it is set |
| `disable` | Server | k3s components that are not installed. The default is none. |
| `write-kubeconfig-mode` | Server | `0644`: the kubeconfig `/etc/rancher/k3s/k3s.yaml` is readable for all users on the node |
| `disable-network-policy` | Server | `true`: no network policy controller. It saves RAM. `NetworkPolicy` resources have no effect. |

The agent node joins the server node at `https://10.0.1.10:6443` (`K3S_URL`).

The k3s components that stay on: CoreDNS, the local-path storage provisioner, the service load balancer (servicelb), metrics-server, the traefik ingress controller and flannel.

## traefik and HTTPS

The cloud-init of the server node writes `/var/lib/rancher/k3s/server/manifests/traefik-config.yaml`. k3s applies it at the start. It sets:

| Setting | What it does |
|---------|--------------|
| Certificate resolver `letsencrypt` | Gets Let's Encrypt certificates with the HTTP-01 challenge on port 80. No email address. |
| `websecure` uses the resolver | Every host name in an `Ingress` gets a certificate. The app needs no annotation. |
| Redirect from `web` to `websecure` | HTTP requests go to HTTPS. |
| Volume (`persistence`) | 128 MiB from the local-path provisioner for `/data/acme.json`. The volume is on the node of the traefik pod, so traefik stays on this node. |

Read "Publish an app with HTTPS" in `OPERATIONS.md`.

## Change the configuration of a live node

A change in a template applies only to a new node. To change a live node:

1. Connect to the node with SSH.
2. Edit `/etc/rancher/k3s/config.yaml`.
3. Restart k3s on the server node:

```bash
sudo systemctl restart k3s
```

On the agent node, restart `k3s-agent` instead.

4. Make the same change in the template, so that a new node gets it.
