provider "google" {
  project = var.project_id
  region  = var.region
}

# Mock infrastructure for Orchestrator (FastAPI) and Evaluator (Java)
# Using Cloud Run as an example of modern serverless container hosting
resource "google_cloud_run_v2_service" "orchestrator" {
  name                = "sentinel-orchestrator"
  location            = var.region
  deletion_protection = false

  template {
    service_account = google_service_account.orchestrator_sa.email
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      env {
        name  = "ENVIRONMENT"
        value = "production"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "SENTINEL_HISTORY_BACKEND"
        value = "firestore"
      }
      env {
        name  = "SENTINEL_FIRESTORE_DATABASE"
        value = google_firestore_database.sentinel.name
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
  name                = "sentinel-evaluator"
  location            = var.region
  deletion_protection = false

  template {
    service_account = google_service_account.evaluator_sa.email
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

# Service Account for Orchestrator
resource "google_service_account" "orchestrator_sa" {
  account_id   = "sentinel-orchestrator"
  display_name = "Sentinel Orchestrator SA"
}

# Service Account for Evaluator
resource "google_service_account" "evaluator_sa" {
  account_id   = "sentinel-evaluator"
  display_name = "Sentinel Evaluator SA"
}

# Allow Orchestrator to invoke the Evaluator
resource "google_cloud_run_v2_service_iam_member" "orchestrator_invokes_evaluator" {
  location = var.region
  name     = google_cloud_run_v2_service.evaluator.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.orchestrator_sa.email}"
}

# Grant Cloud Trace Agent to the orchestrator SA
resource "google_project_iam_member" "orchestrator_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.orchestrator_sa.email}"
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

# Grant deployer SA permission to push Docker images
resource "google_project_iam_member" "deployer_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

# Grant deployer SA permission to deploy Cloud Run services
resource "google_project_iam_member" "deployer_cloud_run" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

# Grant deployer SA permission to act as the compute SA (required for Cloud Run deploys)
resource "google_project_iam_member" "deployer_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_actions_deployer.email}"
}

# Artifact Registry for Docker images
resource "google_artifact_registry_repository" "sentinel_repo" {
  location      = var.region
  repository_id = "sentinel-repo"
  description   = "Docker repository for Sentinel-SDLC agents"
  format        = "DOCKER"
}

# ---------------------------------------------------------------------------
# Firestore — persistent verdict history (Copilot context)
# ---------------------------------------------------------------------------
# Named database ("sentinel") rather than "(default)" so per-environment
# databases in a shared project remain possible later.
resource "google_firestore_database" "sentinel" {
  project                     = var.project_id
  name                        = "sentinel"
  location_id                 = var.region
  type                        = "FIRESTORE_NATIVE"
  concurrency_mode            = "OPTIMISTIC"
  app_engine_integration_mode = "DISABLED"

  # Firestore databases cannot be recreated safely — guard against accidental destroy.
  deletion_policy = "ABANDON"
}

# Composite index that backs get_latest(repo): WHERE repo == X ORDER BY updated_at DESC
resource "google_firestore_index" "history_repo_updated" {
  project    = var.project_id
  database   = google_firestore_database.sentinel.name
  collection = "sentinel_history"

  fields {
    field_path = "repo"
    order      = "ASCENDING"
  }
  fields {
    field_path = "updated_at"
    order      = "DESCENDING"
  }
  fields {
    field_path = "__name__"
    order      = "DESCENDING"
  }
}

# Grant the orchestrator Cloud Run service access to Firestore. datastore.user
# allows read/write on both Firestore Native and Datastore mode databases.
resource "google_project_iam_member" "orchestrator_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.orchestrator_sa.email}"
}
