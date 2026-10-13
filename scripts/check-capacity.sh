#!/usr/bin/env bash
# Usage: scripts/check-capacity.sh [availability domain]
#
# Asks OCI whether a VM.Standard.E2.1.Micro instance can be created now. It
# creates no instance. Prints AVAILABLE or the OCI status, for example
# OUT_OF_HOST_CAPACITY. The exit code is 0 only for AVAILABLE.
# The default availability domain is the one in pulumi/Pulumi.default.yaml.
set -euo pipefail

stack_file="$(dirname "$0")/../pulumi/Pulumi.default.yaml"
ad="${1:-$(sed -n 's/^ *k3s:availability_domain: *//p' "$stack_file")}"
# OCI creates capacity reports in the root compartment (the tenancy).
tenancy="$(sed -n 's/^tenancy *= *//p' ~/.oci/config | head -1)"

status="$(oci compute compute-capacity-report create \
  --compartment-id "$tenancy" \
  --availability-domain "$ad" \
  --shape-availabilities '[{"instanceShape": "VM.Standard.E2.1.Micro"}]' \
  --query 'data."shape-availabilities"[0]."availability-status"' \
  --raw-output)"

echo "$status"
[ "$status" = AVAILABLE ]
