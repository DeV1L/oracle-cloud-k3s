# Setup guide

This guide prepares an Oracle Cloud Infrastructure (OCI) account and the local computer for the project. Then it creates the cluster and configures GitHub.

## Values to collect

The steps below produce values that later steps need. The guide refers to them with these placeholders:

| Placeholder | What it is | From step |
|-------------|------------|-----------|
| `<tenancy OCID>` | The identifier of the tenancy, `ocid1.tenancy.oc1..…` | 2 |
| `<region>` | The home region, for example `eu-frankfurt-1` | 2 |
| `<namespace>` | The Object Storage namespace | 2 |
| `<access key>` | The access key of the Customer Secret Key | 3 |
| `<secret key>` | The secret key of the Customer Secret Key | 3 |
| `<passphrase>` | The Pulumi passphrase | 5 |

## Part 1: before the first deployment

Open a terminal in the repository root. Part 1 runs its commands from there. From step 7 on, the commands run in the `pulumi/` directory.

### 1. Install the tools
- [Python](https://www.python.org/downloads/) 3.10 or newer
- [Pulumi CLI](https://www.pulumi.com/docs/iac/download-install/) 3.268 or newer. Older versions cannot log in to the state bucket
- [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)

### 2. Create the API signing key

The API signing key authenticates the OCI CLI and the Pulumi OCI provider.

1. Open https://cloud.oracle.com and sign in.
2. Click the profile icon in the top right corner. Click **My profile**.
3. Click the **Tokens and keys** tab.
4. In the **API keys** section, click **Add API key**.
5. Select **Generate API key pair**. Click **Download private key**. The browser saves a `.pem` file.
6. Click **Add**.
7. The dialog **Configuration file preview** opens. Copy the text. It has this form:

```text
[DEFAULT]
user=ocid1.user.oc1..<...>
fingerprint=<..>:<..>:<..>
tenancy=ocid1.tenancy.oc1..<...>
region=<...>
key_file=<path to the private key file> # TODO
```

8. Store the `tenancy` value as `<tenancy OCID>` and the `region` value as `<region>`.
9. Create the OCI configuration directory:

```bash
mkdir -p ~/.oci && chmod 700 ~/.oci
```

10. Move the downloaded `.pem` file into it:

```bash
mv <path to the downloaded file>.pem ~/.oci/oci_api_key.pem
```

11. Create the file `~/.oci/config`. Paste the copied text. Replace the `key_file` line with:

```text
key_file=~/.oci/oci_api_key.pem
```

12. Set the file permissions:

```bash
chmod 600 ~/.oci/config ~/.oci/oci_api_key.pem
```

13. Test the configuration. The command prints the Object Storage namespace. Store it as `<namespace>`:

```bash
oci os ns get
```

This command prints `<tenancy OCID>` and `<region>` again:

```bash
grep -E '^(tenancy|region)=' ~/.oci/config
```

### 3. Create the Customer Secret Key

The Customer Secret Key lets Pulumi use the Object Storage bucket through the S3-compatible API.

1. Click the profile icon. Click **My profile**.
2. Click the **Tokens and keys** tab.
3. In the **Customer secret keys** section, click **Generate secret key**.
4. Enter the name `pulumi-state`. Click **Generate secret key**.
5. Copy the **Generated key**. It is shown only once. Store it as `<secret key>`.
6. Click **Close**.
7. In the **Customer secret keys** list, copy the value in the **Access key** column. Store it as `<access key>`.

### 4. Create the state bucket

CAUTION: the S3-compatible API sees only the buckets in one designated compartment. The default is the root compartment. Check it first.

1. Click the profile icon. Click **Tenancy: <tenancy name>**.
2. Find **Object storage settings**. The field **Amazon S3 Compatibility API designated compartment** must show the root compartment. It has the same name as the tenancy.
3. If it shows another compartment, click **Edit object storage settings** and select the root compartment.

Create the bucket in the root compartment, with versioning. The script does nothing when the bucket exists. It prints the backend URL for step 6:

```bash
scripts/bootstrap-state-bucket.sh
```

Check:

```bash
oci os bucket get --name pulumi-state --query 'data.versioning' --raw-output
```

Expected output: `Enabled`.

### 5. Choose a passphrase

Pulumi encrypts the secret values in the state with this passphrase. Choose a long random passphrase. Store it as `<passphrase>`. Without the passphrase, the secrets in the state cannot be read.

### 6. Create the environment file

The project reads its credentials from environment variables. Put them in the file `.env` in the repository root. Git ignores this file.

1. Copy the template:

```bash
cp .env.example .env && chmod 600 .env
```

2. Edit `.env`. Replace every placeholder with its value:

```text
export AWS_ACCESS_KEY_ID='<access key>'
export AWS_SECRET_ACCESS_KEY='<secret key>'
export AWS_REGION='<region>'
export PULUMI_BACKEND_URL='s3://pulumi-state?endpoint=https://<namespace>.compat.objectstorage.<region>.oraclecloud.com&region=<region>&s3ForcePathStyle=true'
export PULUMI_CONFIG_PASSPHRASE='<passphrase>'
```

### 7. Log in to the Pulumi backend and create the stack

1. Load the file into the current shell:

```bash
source .env
```

2. Go to the `pulumi/` directory:

```bash
cd pulumi
```

3. Create the Python environment and install the pinned packages:

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
```

4. Log in to the backend:

```bash
pulumi login "$PULUMI_BACKEND_URL"
```

If the login fails with a connection or signature error, remove `https://` from the `endpoint` value in `.env`. Run `source ../.env` and retry.

5. Open `Pulumi.default.yaml`. Delete the line that starts with `encryptionsalt:`. It belongs to another passphrase, and `pulumi stack init` fails with "incorrect passphrase".
6. Create the stack. Pulumi writes a new `encryptionsalt` line for `<passphrase>`:

```bash
pulumi stack init default
```

## Part 2: the first deployment and GitHub

All commands in part 2 run in the `pulumi/` directory. Start every new terminal with these commands, from the repository root:

```bash
source .env
```

```bash
cd pulumi
```

```bash
source venv/bin/activate
```

### 1. Fill the stack configuration

The stack configuration is in `pulumi/Pulumi.default.yaml`. It holds no secrets. Edit it for the OCI account.

1. Set `oci:region` to `<region>`.
2. Set `k3s:compartment_ocid` to `<tenancy OCID>`. All resources go into the root compartment.
3. Find the availability domain with the quota for the free micro shape:

```bash
oci limits value list --compartment-id <tenancy OCID> --service-name compute --name vm-standard-e2-1-micro-count --scope-type AD --all --query 'data[].{ad:"availability-domain",value:value}' --output table
```

4. Set `k3s:availability_domain` to the availability domain with the value `2`.
5. Print the SSH public keys. RSA keys (`id_rsa.pub`) and Ed25519 keys (`id_ed25519.pub`) both work:

```bash
cat ~/.ssh/*.pub
```
CAUTION: the nodes get the keys only at their first boot. A change to the list applies only to new nodes.

7. Put each public key that may log in to the nodes into the list `k3s:ssh_public_keys`. Use one list entry per key.

The other keys are optional:

| Key | Default | Meaning |
|-----|---------|---------|
| `k3s:k3s_version` | `v1.36.5+k3s1` | k3s version. A new value applies only to new nodes. |
| `k3s:name_prefix` | `k3s` | Prefix for display names and hostnames |
| `k3s:vcn_cidr` | `10.0.0.0/16` | VCN address range |
| `k3s:subnet_cidr` | `10.0.1.0/24` | Subnet address range, inside the VCN range |
| `k3s:server_private_ip` | `10.0.1.10` | Private IP of the server node |
| `k3s:agent_private_ips` | `[10.0.1.11]` | One agent node per entry. The free limit is two nodes in total. |
| `k3s:admin_cidr` | `0.0.0.0/0` | Source address range for SSH (port 22) and the Kubernetes API (port 6443) |
| `k3s:api_name` | `oci-k3s` | An additional name in the server certificate, for example a DNS name |
| `k3s:disable` | `[traefik, metrics-server]` | k3s components that are not installed |
| `k3s:image_ocid` | latest Canonical Ubuntu 24.04 | Image for new nodes |
| `k3s:swap_gb` | `2` | Swap file size per node in GB |

### 2. Check the capacity

OCI does not guarantee capacity for the free micro shape. Ask OCI before the instances are created:

```bash
../scripts/check-capacity.sh
```

The script prints `AVAILABLE` or another status, for example `OUT_OF_HOST_CAPACITY`. Continue only with `AVAILABLE`. Otherwise try again later.

### 3. Create the cluster

1. Show the planned changes:

```bash
pulumi preview
```

2. Create the resources. Type `yes` when Pulumi asks:

```bash
pulumi up
```

3. Show the stack outputs:

```bash
pulumi stack output
```

### 4. Get the kubeconfig and check the nodes

The server node writes a kubeconfig for its public IP to `/home/ubuntu/kubeconfig.yaml`. Any local file name works.

1. Copy the kubeconfig from the server node. The file exists about 2 minutes after `pulumi up` ends:

```bash
scp ubuntu@"$(pulumi stack output server_public_ip)":kubeconfig.yaml ~/.kube/oci-k3s.yaml
```

2. Show the nodes. Both nodes must show `Ready`. The agent node needs about 4 minutes after `pulumi up` ends:

```bash
kubectl --kubeconfig ~/.kube/oci-k3s.yaml get nodes
```

3. Store the kubeconfig in the vault:

```bash
oci vault secret update-base64 --secret-id "$(pulumi stack output kubeconfig_secret_ocid)" --secret-content-content "$(base64 < ~/.kube/oci-k3s.yaml | tr -d '\n')"
```

### 5. Configure GitHub

The workflow `.github/workflows/pulumi.yml` runs `pulumi preview` on pull requests and on pushes to `main` that change `pulumi/`. It runs `pulumi up` only when it is started by hand with the option **apply**.

The workflow reads these values from the repository settings (**Settings**, **Secrets and variables**, **Actions**):

| Name | Type | Value |
|------|------|-------|
| `PULUMI_BACKEND_URL` | variable | The value of `PULUMI_BACKEND_URL` in `.env` |
| `TF_VAR_tenancy_ocid` | variable | `<tenancy OCID>` |
| `TF_VAR_user_ocid` | variable | The `user` value in `~/.oci/config` |
| `TF_VAR_fingerprint` | variable | The `fingerprint` value in `~/.oci/config` |
| `TF_VAR_region` | variable | `<region>` |
| `TF_VAR_private_key` | secret | The content of `~/.oci/oci_api_key.pem` |
| `AWS_ACCESS_KEY_ID` | secret | `<access key>` |
| `AWS_SECRET_ACCESS_KEY` | secret | `<secret key>` |
| `PULUMI_CONFIG_PASSPHRASE` | secret | `<passphrase>` |

Create the variables:

1. Open the repository on https://github.com.
2. Click **Settings**.
3. In the left menu, click **Secrets and variables**, then **Actions**.
4. Click the **Variables** tab.
5. Click **New repository variable**.
6. Enter the name and the value of one variable from the table. Click **Add variable**.
7. Do steps 5 and 6 again for each variable in the table.

Create the secrets:

1. On the same page, click the **Secrets** tab.
2. Click **New repository secret**.
3. Enter the name and the value of one secret from the table. Click **Add secret**.
4. Do steps 2 and 3 again for each secret in the table.

Start the workflow by hand:

1. In the repository, click the **Actions** tab.
2. In the left list, click the workflow **pulumi stack default**.
3. Click **Run workflow**. Keep the branch `main`.
4. To deploy, select **apply (pulumi up)**. 
5. Click the green **Run workflow** button.
6. Click the new run in the list to see its log.
