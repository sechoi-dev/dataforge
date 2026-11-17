# Three-minute demonstration

1. Open <http://localhost:8080> and create a dataset.
2. Upload `load-tests/sample.csv`; open the job and watch persisted progress events.
3. Open its HTML quality report.
4. Change one column and upload a second version.
5. Compare the versions and download the drift/overlap report.
6. Schedule an upload, then cancel it before dispatch.
7. Open Grafana at <http://localhost:3000> (`admin` / `dataforge`).
8. Run the 50-job k6 scenario, scale workers, and show the recorded benchmark table.
9. Stop a worker during a running job and show the abandoned attempt plus lease-recovery event.
10. End with the green Backend CI workflow.
