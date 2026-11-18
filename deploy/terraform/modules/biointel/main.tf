variable "namespace" { type = string }
variable "chart_path" { type = string }
variable "image_repository" { type = string }
variable "image_tag" { type = string }
variable "database_url_secret" { type = string sensitive = true }
variable "redis_url_secret" { type = string sensitive = true }
variable "object_storage_endpoint" { type = string }

resource "kubernetes_namespace" "biointel" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/part-of" = "biointel"
      "pod-security.kubernetes.io/enforce" = "restricted"
    }
  }
}

resource "helm_release" "biointel" {
  name       = "biointel"
  namespace  = kubernetes_namespace.biointel.metadata[0].name
  chart      = var.chart_path
  atomic     = true
  wait       = true
  timeout    = 900
  max_history = 10
  values = [yamlencode({
    image = { repository = var.image_repository, tag = var.image_tag }
    secrets = {
      create = true
      databaseUrl = var.database_url_secret
      redisUrl = var.redis_url_secret
      objectStorageEndpoint = var.object_storage_endpoint
    }
  })]
}

output "namespace" { value = kubernetes_namespace.biointel.metadata[0].name }
output "release_name" { value = helm_release.biointel.name }
