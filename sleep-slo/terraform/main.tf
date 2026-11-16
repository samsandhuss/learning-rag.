# Infrastructure as Code: this file IS the setup. `terraform apply` builds it,
# `terraform destroy` removes it, and applying again builds exactly the same thing.

resource "kubernetes_namespace_v1" "sleep" {
  metadata {
    name   = "sleep-platform"
    labels = var.labels
  }
}

resource "kubernetes_config_map_v1" "slo" {
  metadata {
    name      = "sleep-slo-config"
    namespace = kubernetes_namespace_v1.sleep.metadata[0].name
    labels    = var.labels
  }
  data = {
    "config.json" = jsonencode(var.slo)
  }
}

resource "kubernetes_cron_job_v1" "morning_note" {
  metadata {
    name      = "sleep-morning-note"
    namespace = kubernetes_namespace_v1.sleep.metadata[0].name
    labels    = var.labels
  }
  spec {
    schedule                      = var.schedule
    timezone                      = "Europe/London"
    concurrency_policy            = "Forbid"
    successful_jobs_history_limit = 3
    failed_jobs_history_limit     = 3
    job_template {
      metadata {
        labels = var.labels
      }
      spec {
        backoff_limit = 2
        template {
          metadata {
            labels = var.labels
          }
          spec {
            restart_policy = "OnFailure"
            container {
              name              = "note"
              image             = var.image
              image_pull_policy = "IfNotPresent"
              env {
                name  = "SLEEP_CONFIG"
                value = "/config/config.json"
              }
              resources {
                requests = { cpu = "50m", memory = "64Mi" }
                limits   = { cpu = "200m", memory = "128Mi" }
              }
              volume_mount {
                name       = "config"
                mount_path = "/config"
              }
            }
            volume {
              name = "config"
              config_map {
                name = kubernetes_config_map_v1.slo.metadata[0].name
              }
            }
          }
        }
      }
    }
  }
}

output "what_was_built" {
  value = "Namespace ${kubernetes_namespace_v1.sleep.metadata[0].name}, CronJob ${kubernetes_cron_job_v1.morning_note.metadata[0].name} on schedule '${var.schedule}'"
}
