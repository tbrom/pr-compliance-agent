provider "google" {
  project = var.project_id
  region  = var.region
}

# Mock infrastructure for Orchestrator (FastAPI) and Evaluator (Java)
# Using Cloud Run as an example of modern serverless container hosting
resource "google_cloud_run_v2_service" "orchestrator" {
  name     = "sentinel-orchestrator"
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project_id}/sentinel-orchestrator:latest"
      env {
        name  = "ENVIRONMENT"
        value = "production"
      }
    }
  }
}

resource "google_cloud_run_v2_service" "evaluator" {
  name     = "sentinel-evaluator"
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project_id}/sentinel-evaluator:latest"
    }
  }
}

# IAM Role for the GitHub App webhook to access GCP resources if needed
resource "google_service_account" "github_app_sa" {
  account_id   = "github-app-webhook"
  display_name = "GitHub App Webhook Service Account"
}

# Pub/Sub topic for GitHub Webhook events
resource "google_pubsub_topic" "github_webhooks" {
  name = "github-webhook-events"
}

# Pub/Sub push subscription to trigger the Orchestrator
resource "google_pubsub_subscription" "orchestrator_push" {
  name  = "orchestrator-push-sub"
  topic = google_pubsub_topic.github_webhooks.name

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.orchestrator.uri}/api/github/webhooks"
    
    oidc_token {
      service_account_email = google_service_account.github_app_sa.email
    }
  }
}
