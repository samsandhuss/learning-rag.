terraform {
  required_version = ">= 1.6"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
  }
}

# Points at a local Kubernetes cluster (kind). Swap the context for a cloud cluster later.
provider "kubernetes" {
  config_path    = var.kubeconfig_path
  config_context = var.kube_context
}
