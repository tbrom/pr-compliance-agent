variable "project_id" {
  description = "The ID of the GCP project"
  type        = string
  default     = "sentinel-deployment-492418"
}

variable "region" {
  description = "The GCP region"
  type        = string
  default     = "us-central1"
}

variable "github_repository" {
  description = "The repository path for GitHub Actions WIF (e.g., yourusername/sentinel-agent-core)"
  type        = string
  default     = "tbrom/pr-compliance-agent"
}
