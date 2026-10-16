variable "subscription_id" {
  description = "Azure subscription the report job reads from and runs in."
  type        = string
}

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Resource group holding the Function App and its storage."
  type        = string
  default     = "cis-azure-rg"
}

variable "function_app_name" {
  description = "Globally unique name of the Function App."
  type        = string
}

variable "storage_account_name" {
  description = "Globally unique storage account for Functions runtime state (3-24 lowercase alphanumerics)."
  type        = string
}

variable "service_plan_name" {
  description = "Consumption (Y1) plan name for the Function App."
  type        = string
  default     = "EastUSLinuxDynamicPlan"
}
