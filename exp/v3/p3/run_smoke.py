"""Generate a single cached A/B pair per P3 question with the P1.5 runtime."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
from pathlib import Path
import sys
from time import perf_counter

import p15_runner as runner
from first_round import project_a, validate_a

HERE = Path(__file__).resolve().parent


def main(out):
    cfg = json.loads((HERE / "protocol.json").read_text())
    manifest = json.loads((HERE / "input_manifest.json").read_text())
    for file in ("pools.jsonl", "lengths.csv", "cohorts.json"):
        if runner.file_hash(HERE / file) != manifest["files_sha256"][file]:
            raise ValueError(f"Locked input differs: {file}")
    runner.URL = "http://127.0.0.1:18082/v1"
    sys.path.insert(0, str(HERE / "v2"))
    import compare_models as v2

    size = cfg["pool_size"]
    pools = runner.load_pools(HERE / "pools.jsonl", [size])
    cohorts = json.loads((HERE / "cohorts.json").read_text())["qids"]
    expected = {(size, qid) for qids in cohorts.values() for qid in qids}
    if ({k: len(set(v)) for k, v in cohorts.items()} != cfg["n_by_split"] or set(pools) != expected
            or len(pools) != sum(cfg["n_by_split"].values())):
        raise ValueError("Unexpected or overlapping smoke cohorts")
    with (HERE / "lengths.csv").open(encoding="utf-8") as stream:
        lengths = {(int(row["pool_size"]), row["qid"], row["path"]): row for row in csv.DictReader(stream)}
    if set(lengths) != {(size, qid, route) for _, qid in expected for route in ("top2", "2plus4")}:
        raise ValueError("Missing or extraneous prompt length records")
    for key, row in lengths.items():
        if (int(row["total_tokens"]) > cfg["context"] or int(row["output_reserved"]) != cfg["max_output_tokens"]
                or row["pool_sha256"] != pools[key[:2]]["pool_sha256"]):
            raise ValueError(f"Incompatible prompt budget for {key}")
    qids = sorted((qid for _, qid in expected), key=lambda qid: runner.digest(["p3", cfg["scheduler_seed"], qid]))
    out.mkdir(parents=True, exist_ok=True)
    identity = {"bundle_sha256": runner.file_hash(HERE / "bundle.sha256"), "qid_order": qids}
    identity_path = out / "identity.json"
    if identity_path.exists() and json.loads(identity_path.read_text()) != identity:
        raise ValueError("Cannot resume with a different locked input")
    identity_path.write_text(json.dumps(identity, indent=2) + "\n")

    records = out / "pairs.jsonl"
    success = {}
    for row in runner.read_jsonl(records) if records.exists() else []:
        if row["ok"]:
            if row["qid"] in success or (row["pool_size"], row["qid"]) not in expected:
                raise ValueError("Invalid cached successful pair")
            success[row["qid"]] = row
    runner.service_ready(cfg, cfg["context"])
    warm_config = {**cfg, "routes": {"top2": {"prompt_path": "top2", "first_answer": False}}}
    workers = cfg["client_workers"]
    with records.open("a", encoding="utf-8") as journal, (out / "batches.jsonl").open("a", encoding="utf-8") as batches:
        if not success:
            with (out / "warmups.jsonl").open("a", encoding="utf-8") as warmups:
                for qid in qids[:2]:
                    row = runner.route_one(v2, pools[size, qid], "top2", lengths, warm_config, -1, "warmup")
                    runner.append(warmups, row)
                    if not row["ok"]:
                        raise RuntimeError("P3 warmup did not complete")
        with ThreadPoolExecutor(max_workers=workers) as threads:
            for block, offset in enumerate(range(0, len(qids), workers)):
                pending = [qid for qid in qids[offset:offset+workers] if qid not in success]
                if not pending:
                    continue
                started = perf_counter()
                futures = [threads.submit(runner.route_one, v2, pools[size, qid], "2plus4", lengths, cfg, block, "p3_smoke")
                           for qid in pending]
                failed = 0
                for future in as_completed(futures):
                    row = future.result()
                    runner.append(journal, row)
                    if row["ok"]:
                        success[row["qid"]] = row
                    else:
                        failed += 1
                batch = {"block": block, "submitted": len(pending), "failed": failed,
                         "seconds": perf_counter() - started, "complete_pairs": len(success), "target": len(qids),
                         "recorded_at_utc": runner.utc_now()}
                runner.append(batches, batch)
                print(json.dumps(batch), flush=True)
    if len(success) != len(qids):
        raise RuntimeError("Incomplete P3 cache; successful pairs are saved for a same-config resume")
    tmp = out / "first_round.tmp"
    with tmp.open("w", encoding="utf-8") as stream:
        for qid in sorted(success):
            row = project_a(pools[size, qid], success[qid]["calls"][0], v2.parse_response)
            validate_a(row)
            runner.append(stream, row)
    tmp.replace(out / "first_round.jsonl")
    (out / "complete.json").write_text(json.dumps({"pairs": len(success), "finished_at_utc": runner.utc_now()}) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
