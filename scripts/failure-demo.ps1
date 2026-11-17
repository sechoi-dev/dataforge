param(
    [string]$BaseUrl = "http://localhost:8000"
)

$dataset = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/datasets" `
    -ContentType "application/json" -Body '{"name":"Failure recovery demo"}'

Write-Host "Dataset created: $($dataset.id)"
Write-Host "Set DATAFORGE_FAILURE_INJECTION_STAGE=profiling_columns and restart the worker."
Write-Host "Upload load-tests/sample.csv, observe retry history, then clear the setting."
Write-Host "To demonstrate lease recovery, stop the active worker after a job reaches RUNNING."
Write-Host "The scheduler recovers it after DATAFORGE_WORKER_LEASE_SECONDS and records lease_expired_recovery."
