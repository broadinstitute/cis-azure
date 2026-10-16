output "resource_group_name" {
  value = azurerm_resource_group.cis.name
}

output "function_app_name" {
  value = azurerm_linux_function_app.cis.name
}

output "function_identity_principal_id" {
  value = azurerm_linux_function_app.cis.identity[0].principal_id
}
