from pathlib import Path
import json
import sys


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "constraint-aware-gate-20261122"
sys.path.insert(0, str(PREVIOUS))

import run
from dates import compute
from constraints import compute as old_compute


def main():
    for answer in ("19th century", "end of the eighteenth century", "early ’70s", "the nineties",
                   "September 19, 1993", "1960s", "18th–19th centuries"):
        assert compute("When did it occur?", answer, "").type_mismatch == 0, answer
    for answer in ("Legends of Chima", "Captain Comeback", "American"):
        assert compute("What was the first air date?", answer, "").type_mismatch == 1, answer
    assert compute('Where was "Live By Night" produced in 2003?', "Chicago", "It was made in Chicago.").missing == (
        "2003", "live by night"
    )
    assert old_compute("When did it occur?", "19th century", "").type_mismatch == 1
    protocol = run.load(PREVIOUS / "protocol.json")
    ids = run.load(PREVIOUS / "summary.json")["fit_qids"]
    run.compute = compute
    data = run.development(ids)
    trained = run.train([data[qid] for qid in ids], protocol)
    rules = {}
    for source, target in [("sugeno_old", "old"), ("sugeno_constraints", "repaired")]:
        spec = trained[source]
        rules[target] = {"weights": spec["weights"], "center": protocol["fuzzy_membership_center"],
                         "width": protocol["fuzzy_membership_width"], "training_alpha": spec["alpha"],
                         "training_grid": spec["regularization_search"]}
    old_weights = run.load(PREVIOUS / "summary.json")["models"]["sugeno_old"]["weights"]
    if any(abs(a - b) > 1e-9 for a, b in zip(rules["old"]["weights"], old_weights, strict=True)):
        raise ValueError("The old baseline failed to reproduce")
    out = {"rules": rules, "tie_seed": protocol["tie_seed"], "fit_qids": ids}
    (HERE / "trained.json").write_text(json.dumps(out, indent=2) + "\n")
    print("Date fixture checks passed, old Sugeno weights reproduced, and the repaired policy was fit on P3 training only.")


if __name__ == "__main__":
    main()
