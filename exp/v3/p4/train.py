"""Train the P4 CPU Sugeno smoke models and their frozen-input baselines."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
from statistics import mean
import sys
from time import perf_counter

import torch
from torch import nn

from prepare import load_json, load_records, sha, write_json

HERE = Path(__file__).resolve().parent
RULES = ("LL", "LH", "HL", "HH")


def inverse_sigmoid(p):
    return math.log(p / (1 - p))


def rank_key(qid, score, seed):
    return -score, hashlib.sha256(f"{seed}:{qid}".encode()).hexdigest(), qid


class Sugeno(nn.Module):
    def __init__(self, cfg, target_mean, generator, learn_membership):
        super().__init__()
        center = inverse_sigmoid(cfg["initial_membership_center"])
        width = inverse_sigmoid((cfg["initial_membership_width"] - 0.05) / 0.45)
        self.center_logits = nn.Parameter(torch.full((2,), center), requires_grad=learn_membership)
        self.width_logits = nn.Parameter(torch.full((2,), width), requires_grad=learn_membership)
        initial = target_mean + cfg["consequent_init_sd"] * torch.randn(4, generator=generator)
        self.consequent_logits = nn.Parameter(torch.atanh(initial.clamp(-0.999, 0.999)))

    def effective_parameters(self):
        return self.center_logits.sigmoid(), 0.05 + 0.45 * self.width_logits.sigmoid(), self.consequent_logits.tanh()

    def rule_weights(self, x):
        center, width, _ = self.effective_parameters()
        h_r, h_g = torch.sigmoid((x - center) / width).unbind(dim=-1)
        l_r, l_g = 1 - h_r, 1 - h_g
        return torch.stack((l_r*l_g, l_r*h_g, h_r*l_g, h_r*h_g), dim=-1)

    def forward(self, x):
        weights = self.rule_weights(x)
        consequents = self.consequent_logits.tanh()
        return (weights * consequents).sum(-1) / weights.sum(-1).clamp_min(1e-8)


def tensors(ids, features, targets):
    x = torch.tensor([list(features[qid]["x"].values()) for qid in ids], dtype=torch.float32)
    y = torch.tensor([targets[qid]["delta_f1"] for qid in ids], dtype=torch.float32)
    return x, y


def snapshot(model):
    return {key: value.detach().clone() for key, value in model.state_dict().items()}


def unpack(model):
    with torch.no_grad():
        centers, widths, consequents = (value.tolist() for value in model.effective_parameters())
    return dict(zip(("center_r", "center_bridge", "width_r", "width_bridge", *RULES),
                    (*centers, *widths, *consequents), strict=True))


def mse(pred, target):
    return (pred - target).square().mean()


def fit_one(cfg, variant, alpha, seed, train, val, out):
    xt, yt = train
    xv, yv = val
    generator = torch.Generator(device="cpu").manual_seed(seed)
    model = Sugeno(cfg, yt.mean(), generator, variant == "full_sugeno")
    initial = snapshot(model)
    opt_vars = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.Adam(opt_vars, lr=cfg["learning_rate"])
    best_mse, best_epoch = math.inf, 0
    started = perf_counter()
    history = []
    for epoch in range(1, cfg["max_epochs"] + 1):
        grad_max = 0.
        order = torch.randperm(len(yt), generator=generator)
        for idx in order.split(cfg["batch_size"]):
            opt.zero_grad()
            l2 = torch.cat(opt_vars).square().mean()
            loss = mse(model(xt[idx]), yt[idx]) + alpha * l2
            if not torch.isfinite(loss):
                raise ValueError("Non-finite objective")
            loss.backward()
            if any(p.grad is None or not torch.isfinite(p.grad).all() for p in opt_vars):
                raise ValueError("Missing or non-finite gradient")
            grad_max = max(grad_max, *(p.grad.abs().max().item() for p in opt_vars))
            opt.step()
        with torch.no_grad():
            train_mse = mse(model(xt), yt).item()
            train_objective = train_mse + alpha * torch.cat(opt_vars).square().mean().item()
            val_mse = mse(model(xv), yv).item()
        if not all(math.isfinite(v) for v in (train_mse, train_objective, val_mse)):
            raise ValueError("Non-finite epoch result")
        if val_mse < best_mse:
            best_mse, best_epoch, best_state = val_mse, epoch, snapshot(model)
        history.append({"epoch": epoch, "train_mse": train_mse, "train_objective": train_objective,
                        "val_mse": val_mse, "gradient_max_abs": grad_max, **unpack(model)})
        if epoch - best_epoch >= cfg["patience"]:
            break
    run_path = out / "fits" / variant / f"alpha_{alpha:g}_seed_{seed}"
    run_path.mkdir(parents=True, exist_ok=False)
    with (run_path / "history.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(history[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(history)
    weights = run_path / "weights.pt"
    torch.save(best_state, weights)
    model.load_state_dict(best_state, strict=True)
    reload_model = Sugeno(cfg, yt.mean(), torch.Generator().manual_seed(seed), variant == "full_sugeno")
    reload_model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True), strict=True)
    with torch.inference_mode():
        x = torch.cat((xt, xv))
        prediction = model(x)
        rules = model.rule_weights(x)
        if not torch.allclose(rules.sum(-1), torch.ones(len(x)), atol=1e-6, rtol=0):
            raise ValueError("Rule activation sum is not one")
        if not torch.equal(prediction, reload_model(x)) or not torch.all(prediction.abs() <= 1 + 1e-6):
            raise ValueError("Checkpoint does not exactly reproduce the predictions")
        if mse(model(xv), yv).item() != best_mse:
            raise ValueError("Checkpoint does not match the best validation MSE")
    changed = {k: int(torch.count_nonzero(initial[k] != best_state[k])) for k in initial}
    if not any(changed.values()) or (variant == "consequents_only" and
                                    (changed["center_logits"] or changed["width_logits"])):
        raise ValueError("Unexpected trained parameter state")
    details = {"variant": variant, "alpha": alpha, "seed": seed, "last_epoch": epoch,
               "best_epoch": best_epoch, "val_mse": best_mse,
               "train_mse_at_checkpoint": history[best_epoch-1]["train_mse"],
               "raw_initial": {k: v.tolist() for k,v in initial.items()},
               "raw_checkpoint": {k: v.tolist() for k,v in best_state.items()},
               "changed_parameter_counts": changed, "finite_gradients": True,
               "max_rule_sum_error": float((rules.sum(-1) - 1).abs().max()),
               "checkpoint_replay_exact": True, "effective_parameters": unpack(model),
               "weights_path": str(weights.relative_to(out)), "weights_sha256": sha(weights)}
    write_json(run_path / "checkpoint.json", details)
    return details, prediction.tolist(), perf_counter() - started


def baselines(cfg, ids, train, val, features, targets, gate_file):
    from calibrate_gates_v2 import Pair, candidate_grid, gate_score

    xt, yt = train
    xv, yv = val
    all_x = torch.cat((xt, xv))
    n_train = len(xt)

    def with_intercept(x):
        return torch.cat((torch.ones(len(x), 1, dtype=x.dtype), x), dim=-1)

    design = with_intercept(xt.double())
    penalty = torch.diag(torch.tensor([0., 1., 1.], dtype=torch.float64))
    ridge = []
    for alpha in cfg["ridge_alphas"]:
        w = torch.linalg.solve(design.T @ design + len(xt) * alpha * penalty, design.T @ yt.double())
        fitted = (with_intercept(all_x.double()) @ w).clamp(-1, 1)
        ridge.append((mse(fitted[n_train:], yv.double()).item(), alpha, w.tolist(), fitted.tolist()))
    ridge_mse, alpha, ridge_params, ridge_scores = min(ridge, key=lambda run: (run[0], -run[1]))

    pairs = []
    for qid in ids[:n_train]:
        x, y = features[qid]["x"], targets[qid]
        pairs.append(Pair(qid, x["old_nli_risk"], x["bridge_absent"], y["a_f1"], y["b_f1"], y["a_em"], y["b_em"]))

    def fuzzy_scores(gate):
        return [gate_score(gate["kind"], gate["parameters"], *features[qid]["x"].values()) for qid in ids]

    train_budget = n_train * cfg["fixed_fuzzy_fit_budget_percent"] // 100
    selected_fixed = None
    for params in candidate_grid(pairs):
        scores = fuzzy_scores({"kind": "fuzzy", "parameters": params})
        order = sorted(range(n_train), key=lambda i: rank_key(ids[i], scores[i], cfg["tie_seed"]))
        deltas = [targets[ids[i]]["delta_f1"] for i in order[:train_budget]]
        quality = (math.fsum(deltas), -sum(value < 0 for value in deltas), sum(value > 0 for value in deltas))
        if selected_fixed is None or quality > selected_fixed[0]:
            selected_fixed = quality, params, scores
    _, fixed_params, fixed_scores = selected_fixed
    old_gate = load_json(gate_file)["gates"]["fuzzy"]
    return {
        "fixed_fuzzy": fixed_scores, "locked_v2_fuzzy": fuzzy_scores(old_gate),
        "nli_only": [features[qid]["x"]["old_nli_risk"] for qid in ids],
        "ridge": ridge_scores, "constant_mean": [float(yt.mean())] * len(ids),
    }, {
        "fixed_fuzzy_train_only_budget_percent": cfg["fixed_fuzzy_fit_budget_percent"],
        "fixed_fuzzy_parameters": fixed_params, "locked_v2_fuzzy": old_gate,
        "ridge_alpha": alpha, "ridge_parameters_intercept_then_features": ridge_params,
        "ridge_selected_val_mse": ridge_mse,
        "ridge_grid": [{"val_mse": row[0], "alpha": row[1]} for row in ridge],
        "constant_train_mean": float(yt.mean()),
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--input", required=True, type=Path)
    cli.add_argument("--out", required=True, type=Path)
    cli.add_argument("--v2", required=True, type=Path)
    cli.add_argument("--v2-gate", required=True, type=Path)
    args = cli.parse_args()
    cfg = load_json(HERE / "protocol.json")
    if torch.__version__ != cfg["torch_version"] or torch.cuda.is_available():
        raise ValueError("Expected the frozen PyTorch runtime with CUDA disabled")
    torch.set_num_threads(cfg["torch_threads"])
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_default_dtype(torch.float32)
    manifest = load_json(args.input / "manifest.json")
    if manifest["upstream_sha256"]["p4_protocol"] != sha(HERE / "protocol.json"):
        raise ValueError("P4 protocol differs from the freeze")
    if (manifest["upstream_sha256"]["v2_calibrator"] != sha(args.v2 / "calibrate_gates_v2.py")
            or manifest["upstream_sha256"]["v2_gate"] != sha(args.v2_gate)):
        raise ValueError("V2 code or gate identity differs from the freeze")
    for name, expected in manifest["inputs_sha256"].items():
        if sha(args.input / name) != expected:
            raise ValueError(f"P4 input hash mismatch: {name}")
    sys.path.insert(0, str(args.v2.resolve()))

    features = load_records(args.input / "features.jsonl")
    labels = load_records(args.input / "targets.jsonl")
    if (features.keys() != labels.keys() or dict(Counter(r["split"] for r in labels.values())) != cfg["n_by_split"]
            or any(set(r) != {"qid", "x"} or list(r["x"]) != cfg["features"] for r in features.values())):
        raise ValueError("Feature whitelist or split identity mismatch")
    train_ids, val_ids = [sorted(qid for qid, r in labels.items() if r["split"] == split)
                          for split in ("train", "validation")]
    ids = train_ids + val_ids
    train, val = [tensors(split_ids, features, labels) for split_ids in (train_ids, val_ids)]
    for x, y in (train, val):
        if (x.device.type != "cpu" or x.shape[-1] != 2 or not torch.all((x >= 0) & (x <= 1))
                or not torch.all(y.abs() <= 1)):
            raise ValueError("Unexpected CPU feature/target range")

    args.out.mkdir(parents=True, exist_ok=False)
    runs, selected, scores, runtimes = [], {}, {}, []
    for variant in cfg["variants"]:
        predictions = {}
        for alpha in cfg["alphas"]:
            for seed in cfg["seeds"]:
                run, result, seconds = fit_one(cfg, variant, alpha, seed, train, val, args.out)
                runs.append(run)
                runtimes.append({"variant": variant, "alpha": alpha, "seed": seed, "seconds": seconds})
                predictions[alpha, seed] = result
                print(json.dumps({k: run[k] for k in ("variant", "alpha", "seed", "best_epoch", "last_epoch", "val_mse")}), flush=True)
        cv_mse = {alpha: mean(r["val_mse"] for r in runs if r["variant"] == variant and r["alpha"] == alpha)
                  for alpha in cfg["alphas"]}
        alpha = min(cv_mse, key=lambda value: (cv_mse[value], -value))
        selected[variant] = {"alpha": alpha, "mean_validation_mse_by_alpha": cv_mse,
                             "primary_seed": cfg["primary_seed"]}
        for seed in cfg["seeds"]:
            scores[f"{variant}_seed{seed}"] = predictions[alpha, seed]
    base_scores, base_details = baselines(cfg, ids, train, val, features, labels, args.v2_gate)
    scores.update(base_scores)
    write_json(args.out / "all_run_checkpoints.json", runs)
    write_json(args.out / "model_spec.json", {"feature_order": cfg["features"], "rule_order": RULES,
        "width_range": [0.05, 0.5], "consequent_range": [-1., 1.], "variants": selected,
        "baseline_parameters": base_details, "primary_seed": cfg["primary_seed"]})
    write_json(args.out / "predictions.json", {"qid_order": ids, "scores": scores})
    write_json(args.out / "train_manifest.json", {"python": platform.python_version(), "torch": torch.__version__,
        "dtype": str(torch.get_default_dtype()), "device": "cpu", "threads": torch.get_num_threads(),
        "cuda_available": torch.cuda.is_available(), "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "protocol_sha256": sha(HERE / "protocol.json"), "input_manifest_sha256": sha(args.input / "manifest.json"),
        "train_source_sha256": sha(Path(__file__)), "runs": len(runs), "n_by_split": cfg["n_by_split"]})
    write_json(args.out / "runtime.json", {"runs": runtimes})


if __name__ == "__main__":
    main()
