#!/usr/bin/env bash
# Deploy the CIS report Function App: Terraform creates or updates the Azure
# resources, then the function code is zip-deployed with remote build.
#
# Prerequisites: terraform >= 1.6, Azure CLI logged in (az login) to the
# subscription in infra/terraform.tfvars, and zip.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT/infra"
terraform init -input=false
terraform plan -input=false -out=tfplan
terraform apply -input=false tfplan
rm -f tfplan

APP="$(terraform output -raw function_app_name)"
RG="$(terraform output -raw resource_group_name)"

ZIP="$(mktemp -t cis-azure-func).zip"
trap 'rm -f "$ZIP"' EXIT

cd "$ROOT"
zip -q -r "$ZIP" function_app.py host.json requirements.txt cis_report -x '*__pycache__*'
az functionapp deployment source config-zip \
  --name "$APP" --resource-group "$RG" --src "$ZIP" --build-remote true -o none

echo "Deployed $APP in $RG"
