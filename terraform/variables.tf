variable "project_id" {
  description = "The GCP Project ID"
  type        = string
  default     = "example-mock-project"
}

variable "region" {
  description = "The GCP region"
  type        = string
  default     = "us-central1"
}

variable "github_repository" {
  description = "The repository path for GitHub Actions WIF (e.g., yourusername/sentinel-agent-core)"
  type        = string
  default     = "yourusername/sentinel-agent-core"
}
