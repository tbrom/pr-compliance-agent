output "orchestrator_url" {
  description = "The URL of the Cloud Run Orchestrator service"
  value       = google_cloud_run_v2_service.orchestrator.uri
}

output "evaluator_url" {
  description = "The URL of the Cloud Run Evaluator service"
  value       = google_cloud_run_v2_service.evaluator.uri
}
