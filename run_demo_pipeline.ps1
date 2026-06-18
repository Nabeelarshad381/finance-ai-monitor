# run_demo_pipeline.ps1
# Finance AI news and Trend Monitoring Platform
# Manual demo execution script for project viva presentation

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   🚀 STARTING FINANCE AI NEWS & TREND MONITORING PLATFORM" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check if docker is running and containers are healthy
Write-Host "`n[1/4] Checking Docker Container Health..." -ForegroundColor Yellow
$containers = docker ps --format "{{.Names}} ({{.Status}})"
$required = @("finance_postgres", "finance_n8n", "airflow_scheduler", "airflow_webserver", "finance_streamlit")

foreach ($c in $required) {
    if ($containers -match $c) {
        Write-Host "  ✅ Container $c is running." -ForegroundColor Green
    } else {
        Write-Host "  ❌ Container $c is NOT running. Starting containers..." -ForegroundColor Red
        docker-compose up -d
        Start-Sleep -Seconds 15
        break
    }
}

# 2. Run Data Ingestion & AI Processing
Write-Host "`n[2/4] Triggering News Scrapers, AI Analysis, and Trending Topics..." -ForegroundColor Yellow
Write-Host "Executing pipeline ingestion inside airflow_scheduler container..." -ForegroundColor Gray
docker exec -it airflow_scheduler python /opt/airflow/project/scripts/run_scrapers.py --limit 15

# 3. Trigger Airflow Alert Dispatch
Write-Host "`n[3/4] Dispatching Alerts to n8n Webhook..." -ForegroundColor Yellow
Write-Host "Triggering daily_summary_alert DAG in Airflow..." -ForegroundColor Gray
docker exec -it airflow_scheduler airflow dags trigger daily_summary_alert

Write-Host "`nTriggering breaking_news_alert DAG in Airflow..." -ForegroundColor Gray
docker exec -it airflow_scheduler airflow dags trigger breaking_news_alert

# 4. Display local access URLs
Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "   🎉 PIPELINE EXECUTION STARTED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  📊 Streamlit Dashboard: http://localhost:8501" -ForegroundColor Yellow
Write-Host "  ⚙️  n8n Automation UI:  http://localhost:5678" -ForegroundColor Yellow
Write-Host "  💨 Airflow Webserver:   http://localhost:8080" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Check your email (nabeelarshad3000@gmail.com) shortly for alerts!" -ForegroundColor White
