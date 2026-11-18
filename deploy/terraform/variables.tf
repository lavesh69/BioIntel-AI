variable "namespace" { type = string default = "biointel" }
variable "image_repository" { type = string }
variable "image_tag" { type = string default = "15.6.0" }
variable "database_url_secret" { type = string sensitive = true }
variable "redis_url_secret" { type = string sensitive = true }
variable "object_storage_endpoint" { type = string }
