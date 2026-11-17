import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

const csv = new SharedArray("sample", () => [open("./sample.csv")])[0];
const base = __ENV.BASE_URL || "http://localhost:8000";
const jobs = Number(__ENV.JOBS || 50);
const scenario = __ENV.SCENARIO || "uploadVersion";

export const options = {
  scenarios: {
    uploads: {
      executor: "shared-iterations",
      vus: Number(__ENV.VUS || 10),
      iterations: jobs,
      maxDuration: "10m",
      exec: scenario,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1000"],
  },
};

export function setup() {
  const response = http.post(
    `${base}/api/v1/datasets`,
    JSON.stringify({ name: `Load test ${Date.now()}` }),
    { headers: { "Content-Type": "application/json" } },
  );
  check(response, { "dataset created": (result) => result.status === 201 });
  return { datasetId: response.json("id") };
}

export function uploadVersion(data) {
  const response = http.post(
    `${base}/api/v1/datasets/${data.datasetId}/versions`,
    { file: http.file(csv, `sample-${__VU}-${__ITER}.csv`, "text/csv") },
    { headers: { "Idempotency-Key": `load-${Date.now()}-${__VU}-${__ITER}` } },
  );
  check(response, { "upload accepted": (result) => result.status === 202 });
  sleep(0.1);
}

export function duplicateSubmission(data) {
  const key = `duplicate-${__VU}`;
  const request = () => http.post(
    `${base}/api/v1/datasets/${data.datasetId}/versions`,
    { file: http.file(csv, "duplicate.csv", "text/csv") },
    { headers: { "Idempotency-Key": key } },
  );
  const first = request();
  const second = request();
  check(second, {
    "duplicate returns same job": (result) =>
      result.status === 202 && result.json("job.id") === first.json("job.id"),
  });
}
