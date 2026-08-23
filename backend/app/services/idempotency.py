import hashlib
import json
import uuid


def request_fingerprint(
    *,
    dataset_id: uuid.UUID,
    file_sha256: str,
    filename: str,
    content_type: str,
    description: str | None,
) -> str:
    payload = {
        "content_type": content_type,
        "dataset_id": str(dataset_id),
        "description": description,
        "file_sha256": file_sha256,
        "filename": filename,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def input_object_key(dataset_id: uuid.UUID, file_sha256: str) -> str:
    return f"datasets/{dataset_id}/inputs/{file_sha256}.csv"


def report_object_key(dataset_id: uuid.UUID, version_id: uuid.UUID) -> str:
    return f"datasets/{dataset_id}/reports/{version_id}.json"
