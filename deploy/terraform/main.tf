terraform {
  required_version = ">= 1.7.0"
  required_providers {
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.30" }
    helm       = { source = "hashicorp/helm",       version = "~> 2.13" }
  }
}

module "biointel" {
  source                  = "./modules/biointel"
  namespace               = var.namespace
  chart_path              = abspath("../helm/biointel")
  image_repository        = var.image_repository
  image_tag               = var.image_tag
  database_url_secret     = var.database_url_secret
  redis_url_secret        = var.redis_url_secret
  object_storage_endpoint = var.object_storage_endpoint
}
