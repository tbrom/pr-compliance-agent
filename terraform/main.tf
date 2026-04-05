provider "google" {
  project = var.project_id
  region  = var.region
}

# Mock infrastructure for Orchestrator (FastAPI) and Evaluator (Java)
# Using Cloud Run as an example of modern serverless container hosting
resource "google_cloud_run_v2_service" "orchestrator" {
  name     = "sentinel-orchestrator"
  location = var.region
  deletion_protection = false

  template {
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      env {
        name  = "ENVIRONMENT"
        value = "production"
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }
}

resource "google_cloud_run_v2_service" "evaluator" {
  name     = "sentinel-evaluator"
  location = var.region
  deletion_protection = false

  template {
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
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

# Workload Identity Federation for GitHub Actions
resource "google_iam_workload_identity_pool" "github_actions" {
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Identity pool for GitHub Actions integrations"
}

resource "google_iam_workload_identity_pool_provider" "github_actions" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_actions.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions-provider"
  display_name                       = "GitHub Actions Provider"
  
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository == '${var.github_repository}'"
  
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Allow the GitHub Actions pool to impersonate a deployment Service Account
resource "google_service_account" "github_actions_deployer" {
  account_id   = "github-actions-deployer"
  display_name = "GitHub Actions Deployer SA"
}

resource "google_service_account_iam_member" "workload_identity_user" {
  service_account_id = google_service_account.github_actions_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions.name}/attribute.repository/${var.github_repository}"
}

# Artifact Registry for Docker images
resource "google_artifact_registry_repository" "sentinel_repo" {
  location      = var.region
  repository_id = "sentinel-repo"
  description   = "Docker repository for Sentinel-SDLC agents"
  format        = "DOCKER"
}
