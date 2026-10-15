# Rules for AI agents in this repository

This project creates a two-node k3s cluster on Oracle Cloud (OCI) Always Free resources with Pulumi (Python).

Start with `README.md`, `docs/SETUP.md` and `docs/OPERATIONS.md`. They describe the setup and the daily tasks.

## Hard rules

- Do not commit and do not push. The owner commits.
- Never create a resource outside the OCI Always Free list. Never change a shape, an image or metadata in a way that replaces an instance as a side effect.
- A vault must have the type `DEFAULT` and its keys must be software-protected. A virtual private vault and HSM keys cost money.
- Never write a secret into the repository: no private keys, no tokens, no passphrases, no kubeconfig files. The repository is public. Never print a secret value in your output.
- This is a home lab. Keep every part simple. Do not add resources, configuration keys, checks or security measures that the owner did not ask for.
- When a documented fact is wrong or a step does not work, stop and ask the owner. Do not guess.

## Deploying and testing

You build and test against the real OCI account. The test is `pulumi preview`, then `pulumi up`, then a check of the result. There are no unit tests.

- Before you create or replace an instance, run `scripts/check-capacity.sh`. Continue only when it prints `AVAILABLE`. Capacity for the free micro shape is not guaranteed, and a deleted instance can take days to get back.
- Replace an instance only on purpose, never as a side effect of another change. Read every preview for the word "replace". Tell the owner about every replacement.
- Only one `pulumi up` runs at a time. When the state is locked, wait. Never cancel a lock without the owner.
- `pulumi destroy` of the whole stack needs the owner's request.
- Credentials: the owner provides `~/.oci/config` (profile `DEFAULT`) and the file `.env` in the repository root with `PULUMI_BACKEND_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` and `PULUMI_CONFIG_PASSPHRASE`. It also puts the OCI CLI (`~/bin/oci`) on the `PATH`. Your shell does not load it on its own: run `source .env` from the repository root at the start of every shell. If the file is missing, ask the owner. Never read `.env` aloud and never copy it anywhere.

Commands, from the repository root:

1. `source .env`
2. `cd pulumi && source venv/bin/activate` (create the venv first when it is missing: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`)
3. `pulumi login "$PULUMI_BACKEND_URL"` and `pulumi stack select default`
4. `pulumi preview`
5. `pulumi up`
6. `pulumi stack output`, then `kubectl get nodes` when the cluster exists. Get the kubeconfig as `docs/OPERATIONS.md` describes

## Facts about OCI and this setup

Verified in the owner's tenancy (home region `eu-frankfurt-1`) in October 2026.

- Always Free limits that matter here: 2 micro instances, only in availability domain AD-1 of this tenancy; 1 reserved public IP; 1 network load balancer; 1 vault of type `DEFAULT`; 2 VCNs; 200 GB block storage.
- The network load balancer holds the reserved public IP. It forwards 6443 to the server node, and 80 and 443 to both nodes. Each node has an ephemeral public IP for internet access and SSH, because a NAT gateway is not free.
- A deleted vault waits 7 to 30 days for its deletion and can still count against the limit of 1. To rebuild the cluster, keep the vault ("Rebuild the cluster and keep the vault" in `docs/OPERATIONS.md`).
- OCI rejects changes to `user_data` and `ssh_authorized_keys`, and cloud-init runs only at the first boot. Therefore the instances are protected and ignore changes to the image and the metadata. A cloud-init change applies only to new nodes.
- To test a cloud-init change without a new instance, copy the new bootstrap script to the live node and run it there. The script is safe to run a second time.
- A replacement deletes the old instance first (`delete_before_replace`): the fixed private IP and the micro quota allow no second instance. A replaced agent node joins only after `kubectl delete node <name>`.
- The security list is the only firewall. The Ubuntu image rejects inbound and forwarded traffic with iptables. The cloud-init removes these two reject rules.
- Pulumi creates the reserved public IP before the nodes and passes it to the cloud-init. The server node puts it and the DNS name `k3s:api_name` (in `Pulumi.yaml`, not in the stack file) into the k3s certificate. The kubeconfig `/home/ubuntu/kubeconfig.yaml` uses the DNS name.
- traefik gets Let's Encrypt certificates (HTTP-01). They are on a volume on the node of the traefik pod, so a replacement of this node requests them again. Let's Encrypt allows 5 identical certificates in 7 days: use the staging server for test rebuilds.
- The scheduler places pods by memory requests. After a replacement, the system pods can start on the server node, which then swaps. Move them ("The server node is slow after a replacement" in `docs/OPERATIONS.md`).
- `Pulumi.yaml` sets `refresh: always`, so every preview sees resources that were deleted outside Pulumi.
- The Pulumi CLI must be 3.268 or newer. Version 3.256 cannot log in to the state bucket (`BadDigest`).
- Each node has 1 GB of RAM. The server node uses about 600 MB and some swap after the start, so little room is left for workloads. The nodes use Ubuntu 24.04 Minimal, and the cloud-init turns off services that a node does not need.

## Code style

The reference project is `/home/ubuntu/git/durantic/infra-cloud` (Pulumi, Python). Ask for folder access when you need to read it. Its style, in short:

- Directory `pulumi/` with `Pulumi.yaml`, `Pulumi.<stack>.yaml`, `requirements.txt`, `__main__.py` and a `components/` package.
- Each unit of infrastructure is a `pulumi.ComponentResource` subclass in its own module. The type token has the form `oracle-cloud-k3s:<area>:<ClassName>`.
- Defaults are class constants named `DEFAULT_*`. Configuration is read in one place and passed in as a typed object.
- Child resources get `opts=pulumi.ResourceOptions(parent=self)`. The component ends with `self.register_outputs(...)` and `pulumi.export(...)` for stack outputs.
- `requirements.txt` has exact pins and a comment that says why.
- Docstrings on modules and classes. Comments explain why, not what. Type hints on public functions.
- No new dependencies without the owner's approval.

## Documentation rules

Write plain English, about 70 % of the way to ASD-STE100:

- Short sentences. At most 20 words in a procedure step, 25 in a description.
- One instruction per sentence. Start a step with a verb: "Open", "Run", "Copy".
- Active voice and present tense.
- One word for one thing. Use the glossary below. Do not use synonyms for these terms.
- No idioms, no filler words, no "please", no humour.
- Write the full form, not a contraction: "do not", not "don't".
- Explain an abbreviation the first time you use it.
- Use a numbered list for steps and a table for options.
- Put a warning before the step it belongs to, in the form "CAUTION: ...".
- Commands are exact and complete. Put each command in its own code block.

Glossary:

| Term | Meaning |
|------|---------|
| server node | The k3s node that runs the control plane (`k3s-server`) |
| agent node | A k3s node that runs workloads only (`k3s-agent-1`) |
| stack | The Pulumi stack `default` |
| state bucket | The OCI Object Storage bucket that holds the Pulumi state |
| vault | The OCI Vault `k3s-vault` that holds the join token and the kubeconfig |
| API signing key | The OCI key pair that authenticates the Pulumi OCI provider and the OCI CLI |
| Customer Secret Key | The OCI credential for the S3-compatible API (state bucket) |
| passphrase | The value of `PULUMI_CONFIG_PASSPHRASE` |
| owner | The person who runs this project |
