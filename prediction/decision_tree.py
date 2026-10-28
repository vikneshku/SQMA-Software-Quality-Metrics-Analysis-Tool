"""
prediction/decision_tree.py
Decision Tree (Feature 6) - explainable risk classifier.

Features used: loc, complexity, defect_density, reopen_rate, security_issues
Label: risk_class in {Low, Medium, High}

NOTE (documented / honest limitation): a real classroom/college project
rarely has a large labeled historical defect dataset. This module trains
on a rule-derived synthetic dataset generated from documented thresholds,
so the tree's decisions are explainable and defensible. If you supply
your own labeled historical data later, swap `_generate_training_data()`
for a loader of your real dataset — the rest of the pipeline is unchanged.
"""
import random
from sklearn.tree import DecisionTreeClassifier, export_text


FEATURE_NAMES = ["loc", "complexity", "defect_density", "reopen_rate", "security_issues"]


def _label_from_rules(loc, complexity, defect_density, reopen_rate, security_issues):
    score = 0
    score += 1 if complexity > 10 else (0.5 if complexity > 5 else 0)
    score += 1 if defect_density > 8 else (0.5 if defect_density > 3 else 0)
    score += 1 if reopen_rate > 20 else (0.5 if reopen_rate > 8 else 0)
    score += 1 if security_issues > 2 else (0.5 if security_issues > 0 else 0)
    score += 0.5 if loc > 800 else 0

    if score >= 2.5:
        return "High"
    if score >= 1.0:
        return "Medium"
    return "Low"


def _generate_training_data(n=450, seed=42):
    """Rule-derived synthetic dataset. Each sample is drawn from one of three
    realistic 'project profiles' (healthy / moderate / unhealthy) so that all three
    risk classes (Low, Medium, High) are represented; the label itself is always
    produced by _label_from_rules() above."""
    rnd = random.Random(seed)
    profiles = [
        dict(loc=(20, 600),   cx=(1, 6),   dd=(0, 3),  rr=(0, 8),   sec=(0, 0)),   # healthy
        dict(loc=(200, 1500), cx=(4, 12),  dd=(2, 9),  rr=(5, 25),  sec=(0, 3)),   # moderate
        dict(loc=(800, 2500), cx=(10, 30), dd=(6, 20), rr=(15, 50), sec=(2, 6)),   # unhealthy
    ]
    X, y = [], []
    for i in range(n):
        p = profiles[i % 3]
        loc = rnd.randint(*p["loc"])
        complexity = round(rnd.uniform(*p["cx"]), 1)
        defect_density = round(rnd.uniform(*p["dd"]), 2)
        reopen_rate = round(rnd.uniform(*p["rr"]), 2)
        security_issues = rnd.randint(*p["sec"])
        label = _label_from_rules(loc, complexity, defect_density, reopen_rate, security_issues)
        X.append([loc, complexity, defect_density, reopen_rate, security_issues])
        y.append(label)
    return X, y


def _serialize_tree(clf, sample_row):
    """Convert the trained scikit-learn tree into plain nested dicts so the page
    can draw it as a flowchart (root node -> decision nodes -> leaf nodes), and
    work out the exact path that this project's feature values follow."""
    t = clf.tree_
    classes = [str(c) for c in clf.classes_]
    path_ids = [int(i) for i in clf.decision_path([sample_row]).indices]

    def build(node):
        samples = int(t.n_node_samples[node])
        counts = t.value[node][0]
        cls = classes[int(counts.argmax())]
        if t.children_left[node] == t.children_right[node]:      # leaf
            return {"id": node, "type": "leaf", "cls": cls, "samples": samples, "children": []}
        feat = FEATURE_NAMES[t.feature[node]]
        thr = round(float(t.threshold[node]), 2)
        return {"id": node, "type": "decision", "label": f"{feat} <= {thr}", "feature": feat,
                "threshold": thr, "cls": cls, "samples": samples,
                "children": [build(int(t.children_left[node])), build(int(t.children_right[node]))]}

    tree = build(0)

    # human-readable path: which question was asked, the project's value, the answer
    steps, node = [], 0
    while t.children_left[node] != t.children_right[node]:
        feat = FEATURE_NAMES[t.feature[node]]
        thr = round(float(t.threshold[node]), 2)
        val = sample_row[t.feature[node]]
        go_left = val <= thr
        steps.append({"text": f"{feat} <= {thr} ?", "value": val, "answer": "Yes" if go_left else "No"})
        node = int(t.children_left[node] if go_left else t.children_right[node])
    return tree, path_ids, steps


def train_and_predict(loc, complexity, defect_density, reopen_rate, security_issues) -> dict:
    X, y = _generate_training_data()
    clf = DecisionTreeClassifier(max_depth=4, random_state=42)
    clf.fit(X, y)

    sample = [[loc, complexity, defect_density, reopen_rate, security_issues]]
    prediction = str(clf.predict(sample)[0])
    probs = clf.predict_proba(sample)[0]
    classes = [str(c) for c in clf.classes_]
    prob_map = {c: round(float(p), 3) for c, p in zip(classes, probs)}

    importances = dict(zip(FEATURE_NAMES, [round(float(i), 3) for i in clf.feature_importances_]))
    tree_rules = export_text(clf, feature_names=FEATURE_NAMES)
    tree_structure, path_ids, path_steps = _serialize_tree(clf, sample[0])

    return {
        "predicted_risk": prediction,
        "probabilities": prob_map,
        "feature_importances": importances,
        "tree_rules": tree_rules,
        "tree_structure": tree_structure,
        "path_ids": path_ids,
        "path_steps": path_steps,
        "n_training_samples": len(X),
        "note": "Trained on a rule-derived synthetic dataset for explainability; "
                "replace with real historical data when available.",
    }
