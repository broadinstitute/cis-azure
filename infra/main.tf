resource "azurerm_resource_group" "cis" {
  name     = var.resource_group_name
  location = var.location
}

# Holds Functions runtime state and the Consumption-plan code share. It does not hold report data.
resource "azurerm_storage_account" "functions" {
  name                            = var.storage_account_name
  resource_group_name             = azurerm_resource_group.cis.name
  location                        = azurerm_resource_group.cis.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
}

resource "azurerm_service_plan" "cis" {
  name                = var.service_plan_name
  resource_group_name = azurerm_resource_group.cis.name
  location            = azurerm_resource_group.cis.location
  os_type             = "Linux"
  sku_name            = "Y1"
}

resource "azurerm_linux_function_app" "cis" {
  name                       = var.function_app_name
  resource_group_name        = azurerm_resource_group.cis.name
  location                   = azurerm_resource_group.cis.location
  service_plan_id            = azurerm_service_plan.cis.id
  storage_account_name       = azurerm_storage_account.functions.name
  storage_account_access_key = azurerm_storage_account.functions.primary_access_key
  https_only                 = true

  # Deploys use the Azure CLI's bearer token, not basic-auth publishing credentials.
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false

  identity {
    type = "SystemAssigned"
  }

  site_config {
    minimum_tls_version = "1.2"
    ftps_state          = "Disabled"

    application_stack {
      python_version = "3.12"
    }
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME       = "python"
    AZURE_SUBSCRIPTION_ID          = var.subscription_id
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
  }
}

# Read-only access to Defender for Cloud regulatory compliance data for the subscription.
resource "azurerm_role_assignment" "function_security_reader" {
  scope                = "/subscriptions/${var.subscription_id}"
  role_definition_name = "Security Reader"
  principal_id         = azurerm_linux_function_app.cis.identity[0].principal_id
}
