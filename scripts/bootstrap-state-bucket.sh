#!/usr/bin/env bash
# Usage: scripts/bootstrap-state-bucket.sh
#
# Creates the Pulumi state bucket "pulumi-state" in the root compartment, with
# versioning and no public access. Creates nothing when the bucket exists.
# Prints the value of PULUMI_BACKEND_URL for the file .env.
set -euo pipefail

bucket=pulumi-state
tenancy="$(sed -n 's/^tenancy *= *//p' ~/.oci/config | head -1)"
region="$(sed -n 's/^region *= *//p' ~/.oci/config | head -1)"
namespace="$(oci os ns get --query data --raw-output)"

# The S3-compatible API sees only the buckets in the root compartment (the default).
if oci os bucket get --bucket-name "$bucket" >/dev/null 2>&1; then
  echo "Bucket $bucket exists."
else
  oci os bucket create --compartment-id "$tenancy" --name "$bucket" \
    --versioning Enabled --public-access-type NoPublicAccess >/dev/null
  echo "Bucket $bucket created."
fi

echo "PULUMI_BACKEND_URL='s3://$bucket?endpoint=https://$namespace.compat.objectstorage.$region.oraclecloud.com&region=$region&s3ForcePathStyle=true'"
