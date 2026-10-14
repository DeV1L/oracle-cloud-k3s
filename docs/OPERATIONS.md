# Operations guide

This guide describes daily tasks and troubleshooting for the cluster. Run all commands in the `pulumi/` directory. Start every new terminal with these commands, from the repository root:

```bash
source .env
```

```bash
cd pulumi
```

```bash
source venv/bin/activate
```

## Get the kubeconfig from the vault

Read the kubeconfig into a local file. Any file name works:

```bash
oci secrets secret-bundle get --secret-id "$(pulumi stack output kubeconfig_secret_ocid)" --query 'data."secret-bundle-content".content' --raw-output | base64 -d > ~/.kube/oci-k3s.yaml
```

Use it with `kubectl --kubeconfig ~/.kube/oci-k3s.yaml` or `export KUBECONFIG=~/.kube/oci-k3s.yaml`.

## Update the kubeconfig in the vault

Do this when the server node is new or when the API name changed. Copy the kubeconfig from the server node and store it in the vault. Do the steps in the setup guide, part 2, step 4.

## Read the join token from the vault

```bash
oci secrets secret-bundle get --secret-id "$(pulumi stack output join_token_secret_ocid)" --query 'data."secret-bundle-content".content' --raw-output | base64 -d
```

## Connect to a node with SSH

The user is `ubuntu`. SSH is open from `k3s:admin_cidr`.

1. Connect to the server node:

```bash
ssh ubuntu@"$(pulumi stack output server_public_ip)"
```

2. Show the public IPs of the nodes:

```bash
# Server
pulumi stack output server_public_ip

# Agent
pulumi stack output agent_public_ip
```

## Check the capacity

The script asks OCI whether a free micro instance can be created now. It creates no instance.

```bash
../scripts/check-capacity.sh
```

The script prints `AVAILABLE` or another status, for example `OUT_OF_HOST_CAPACITY`. The exit code is 0 only for `AVAILABLE`.

## Replace a node

The instances are protected. Pulumi does not delete or replace them as a side effect of another change. A replacement is a deliberate step.

CAUTION: the old instance is deleted first. When OCI has no capacity, the node is gone until capacity comes back. This can take days.

1. Show the resource names (URNs) of the instances:

```bash
pulumi stack --show-urns | grep 'Instance::'
```

2. Check the capacity. Continue only with `AVAILABLE`:

```bash
../scripts/check-capacity.sh
```

3. Remove the protection from the instance. Use the URN from step 1:

```bash
pulumi state unprotect '<instance URN>'
```

4. Replace the instance. Read the preview. Only this instance and its public IP may change:

```bash
pulumi up --replace '<instance URN>'
```

The new instance gets the protection again from the code. The server node keeps its reserved public IP. An agent node gets a new ephemeral public IP.

5. Remove the old host key of the node from the local SSH client:

```bash
ssh-keygen -R <node public IP>
```

After a replacement of an agent node, delete its old node object. The new node has the same name, so the server node rejects it until then. The new node joins about 1 minute later:

```bash
kubectl --kubeconfig ~/.kube/oci-k3s.yaml delete node <agent node name>
```

A new server node starts a new, empty cluster. To replace the server node, replace both nodes.

## Replace both nodes

This makes a new, empty cluster with the same network, vault, join token and server public IP. All workloads and their data are lost.

CAUTION: both old instances are deleted first. When OCI has no capacity, the nodes are gone until capacity comes back. This can take days.

1. Check the capacity. Continue only with `AVAILABLE`:

```bash
../scripts/check-capacity.sh
```

2. Remove the protection from the instances. Only the instances are protected:

```bash
pulumi state unprotect --all --yes
```

3. Show the resource names (URNs) of the instances:

```bash
pulumi stack --show-urns | grep 'Instance::'
```

4. Replace both instances. Use the URNs from step 3. Read the preview. Only the instances and their public IPs may change:

```bash
pulumi up --replace '<server instance URN>' --replace '<agent instance URN>'
```

5. Remove the old host key of the server node from the local SSH client. The agent node has a new public IP:

```bash
ssh-keygen -R "$(pulumi stack output server_public_ip)"
```

6. Wait about 5 minutes for the first boot. Copy the kubeconfig from the server node and store it in the vault. Do the steps in the setup guide, part 2, step 4.

The agent node joins the new cluster on its own.

## Upgrade k3s

The value `k3s:k3s_version` applies only to new nodes. Upgrade the running nodes over SSH. Upgrade the server node first.

1. Set the new version for new nodes:

```bash
pulumi config set k3s:k3s_version <new version>
```

2. Connect to the server node with SSH. Run the installer with the new version:

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION='<new version>' sh -s - server
```

3. Connect to the agent node with SSH. Run the installer with the new version:

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION='<new version>' K3S_URL='https://10.0.1.10:6443' sh -s - agent
```

4. Check the versions of the nodes:

```bash
kubectl get nodes
```

## Use a DNS name for the Kubernetes API

The server certificate contains the public IP of the server node and the API name `k3s:api_name`. With a DNS name as API name, the kubeconfig can use the name instead of the IP.

1. Create a DNS `A` record for the name. Point it to the public IP of the server node.
2. Set the API name for new nodes:

```bash
pulumi config set k3s:api_name <DNS name>
```

3. Connect to the server node with SSH. Open `/etc/rancher/k3s/config.yaml`. Add the DNS name to the list `tls-san`.
4. Restart k3s on the server node. k3s adds the name to the certificate:

```bash
sudo systemctl restart k3s
```

5. In the local kubeconfig, change the `server:` line to `https://<DNS name>:6443`.
6. Store the kubeconfig in the vault. See the setup guide, part 2, step 4.

## Rebuild the cluster and keep the vault

This deletes the nodes, the public IPs and the network, and creates them again. The vault, the key, the secrets and the join token stay. The new nodes use the same join token.

CAUTION: this deletes the cluster and all data in it. The server node gets a new public IP. The free capacity can take days to come back.

1. Check the capacity. Continue only with `AVAILABLE`:

```bash
../scripts/check-capacity.sh
```

2. Remove the protection from the instances:

```bash
pulumi state unprotect --yes 'urn:pulumi:default::oracle-cloud-k3s::oracle-cloud-k3s:cluster:K3sClusterComponent$oci:Core/instance:Instance::cluster-server' 'urn:pulumi:default::oracle-cloud-k3s::oracle-cloud-k3s:cluster:K3sClusterComponent$oci:Core/instance:Instance::cluster-agent-1'
```

3. Delete the network and the cluster. Type `yes` when Pulumi asks:

```bash
pulumi destroy --target 'urn:pulumi:default::oracle-cloud-k3s::oracle-cloud-k3s:network:NetworkComponent**' --target 'urn:pulumi:default::oracle-cloud-k3s::oracle-cloud-k3s:cluster:K3sClusterComponent**'
```

4. Create the network and the cluster again. The instances get the protection again from the code:

```bash
pulumi up
```

5. Copy the kubeconfig from the server node and store it in the vault. Do the steps in the setup guide, part 2, step 4.

The destroy needs about 2 minutes. `pulumi up` needs about 1 minute. The nodes are `Ready` about 4 minutes later.

## Destroy everything

CAUTION: this deletes the cluster and all data in it. OCI does not delete the vault, the key and the secrets at once. It schedules the deletion for a date in 7 to 30 days.

CAUTION: an Always Free tenancy allows one vault (limit `virtual-vault-count`). A vault that waits for its deletion date can still count against this limit. Then a new `pulumi up` cannot create a vault until OCI has deleted the old one. To build the cluster again soon, use "Rebuild the cluster and keep the vault".

1. Remove the protection from all resources:

```bash
pulumi state unprotect --all
```

2. Delete all resources of the stack. Type `yes` when Pulumi asks:

```bash
pulumi destroy
```

The state bucket stays. Delete it in the OCI console when it is not needed.

## Troubleshooting

### `pulumi up` fails with "Out of host capacity"

OCI has no free micro capacity in the availability domain. OCI created no instance. The other resources stay in the state.

1. Wait. Capacity often comes back after some hours.
2. Run `../scripts/check-capacity.sh`.
3. When it prints `AVAILABLE`, run `pulumi up`.

### The agent node does not join

1. Connect to the agent node with SSH.
2. Read the bootstrap log:

```bash
sudo cat /var/log/k3s-bootstrap.log
```

3. Read the log of the k3s agent:

```bash
sudo journalctl -u k3s-agent --no-pager -n 100
```

4. Check that the agent node has internet access. The agent node needs its public IP for this:

```bash
curl -sI https://get.k3s.io
```

5. Check that the agent node reaches the server node on port 6443:

```bash
curl -sk https://10.0.1.10:6443/ping
```

The expected output is `pong`. When the command fails, read "Traffic is blocked".

### Traffic is blocked

The OCI security list is the only firewall. The cloud-init removes the reject rules of the host firewall (iptables) in the Ubuntu image.

1. Add the port to the security list in `components/network.py`.
2. Run `pulumi up`.
3. When the port is still blocked, connect to the node with SSH. Show the host firewall rules:

```bash
sudo iptables -S INPUT
```

The output must not contain a `REJECT` rule with `icmp-host-prohibited`.

### k3s is not ready

1. Connect to the server node with SSH.
2. Read the bootstrap log. The last line is `k3s bootstrap done` when the setup is complete:

```bash
sudo cat /var/log/k3s-bootstrap.log
```

When the log ends with `No public IP found`, the node had no internet access for 10 minutes. The server node needs its public IP for internet access. Check the IP in the OCI console, then do step 5.

3. Read the cloud-init log:

```bash
sudo cat /var/log/cloud-init-output.log
```

4. Read the log of k3s:

```bash
sudo journalctl -u k3s --no-pager -n 100
```

5. Run the bootstrap script again. It is safe to run a second time:

```bash
sudo /usr/local/sbin/k3s-bootstrap.sh
```

### Oracle reclaims an idle instance

Oracle can delete an Always Free instance that is idle for 7 days. Idle means: CPU utilization (95th percentile) below 20 % and network utilization below 20 %. Oracle sends an email before it acts.

- Run a workload on each node.
- Read the emails from Oracle.
- Upgrade the account to Pay As You Go. The rule does not apply to such accounts. Resources inside the Always Free limits stay free.

When Oracle deleted an instance, do the steps in "A resource was deleted outside Pulumi".

### A resource was deleted outside Pulumi

The state still lists the resource, for example an instance deleted in the OCI console. A plain `pulumi preview` does not see this. For a deleted instance, it fails with "no private IP ... The instance was deleted outside Pulumi".

1. Check the capacity. Continue only with `AVAILABLE`:

```bash
../scripts/check-capacity.sh
```

2. Show the changes. The `--refresh` option reads the real resources from OCI first:

```bash
pulumi preview --refresh
```

3. Create the missing resources:

```bash
pulumi up --refresh
```

A new agent node joins after its old node object is deleted: see "Replace a node". A missing server node starts a new, empty cluster: see "Replace a node" too.

### The state is locked

Only one `pulumi up` can run at a time. Another run holds the lock: a run on another machine, or the GitHub workflow.

1. Wait until the other run ends. To see the GitHub workflow runs, open the **Actions** tab of the repository on GitHub.

2. When no other run is active, the lock is left over from a run that stopped. Remove it:

```bash
pulumi cancel
```
