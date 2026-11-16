variable "kubeconfig_path" {
  type    = string
  default = "~/.kube/config"
}

variable "kube_context" {
  type    = string
  default = "kind-sleep"
}

variable "image" {
  description = "Container image for the morning note"
  type        = string
  default     = "sleep-slo:local"
}

variable "schedule" {
  description = "When the note runs (cron format)"
  type        = string
  default     = "0 7 * * *"
}

variable "slo" {
  description = "Service Level Objective settings"
  type = object({
    target_sleep_minutes = number
    bedtime_cutoff       = string
    slo_target           = number
    window_days          = number
  })
  default = {
    target_sleep_minutes = 450
    bedtime_cutoff       = "00:30"
    slo_target           = 0.8
    window_days          = 30
  }
  validation {
    condition     = var.slo.slo_target > 0 && var.slo.slo_target < 1
    error_message = "slo_target must be between 0 and 1, e.g. 0.8 for 80% good nights."
  }
}

# Policy as code: every resource must say who owns it and who pays (FinOps).
variable "labels" {
  type = map(string)
  default = {
    owner       = "sleep-platform"
    cost-centre = "personal-learning"
  }
  validation {
    condition     = contains(keys(var.labels), "owner") && contains(keys(var.labels), "cost-centre")
    error_message = "Labels must include owner and cost-centre."
  }
}
