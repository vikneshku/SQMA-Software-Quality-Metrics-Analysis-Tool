"""
prediction/defect_prediction.py
Defect Prediction - probability of defects from software metrics (Random Forest).

Features (5): loc, complexity, defect_density, reopen_rate, security_issues
(the duplicate module_size feature was removed - it was identical to loc).

Training data is SYNTHETIC (rule-derived), generated in a stratified way so both
classes get an equal share, trained with class_weight="balanced", and scored on a
25% hold-out set whose accuracy is shown on the page.
"""
import math
import random

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

FEATURE_NAMES = ["loc", "complexity", "defect_density", "reopen_rate", "security_issues"]


def _defect_probability(loc, complexity, defect_density, reopen_rate, security_issues):
    risk = (0.02 * complexity + 0.05 * defect_density + 0.02 * reopen_rate
            + 0.15 * security_issues + 0.0006 * loc)
    return 1.0 / (1.0 + math.exp(-2.0 * (risk - 1.9)))      # logistic around the mid-point


def _generate_training_data(n=500, seed=7):
    """Stratified generation: accept candidates until each class has exactly n/2 rows."""
    rnd = random.Random(seed)
    quota = {0: n // 2, 1: n - n // 2}
    X, y = [], []
    guard = 0
    while (quota[0] > 0 or quota[1] > 0) and guard < 200000:
        guard += 1
        loc = rnd.randint(20, 3000)
        complexity = round(rnd.uniform(1, 30), 1)
        defect_density = round(rnd.uniform(0, 20), 2)
        reopen_rate = round(rnd.uniform(0, 50), 2)
        security_issues = rnd.randint(0, 6)
        p = _defect_probability(loc, complexity, defect_density, reopen_rate, security_issues)
        label = 1 if rnd.random() < p else 0
        if quota[label] <= 0:
            continue
        quota[label] -= 1
        X.append([loc, complexity, defect_density, reopen_rate, security_issues])
        y.append(label)
    return X, y


def predict_defect_risk(loc, complexity, defect_density, reopen_rate, security_issues) -> dict:
    X, y = _generate_training_data()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=7, stratify=y)
    clf = RandomForestClassifier(n_estimators=80, max_depth=6, random_state=7, class_weight="balanced")
    clf.fit(X_tr, y_tr)
    holdout = round(float(accuracy_score(y_te, clf.predict(X_te))), 3)
    clf.fit(X, y)                                            # final model uses all rows

    sample = [[loc, complexity, defect_density, reopen_rate, security_issues]]
    prob = clf.predict_proba(sample)[0]
    classes = list(clf.classes_)
    defect_probability = round(float(prob[classes.index(1)]) if 1 in classes else 0.0, 3)
    importances = dict(zip(FEATURE_NAMES, [round(float(i), 3) for i in clf.feature_importances_]))

    level = "High" if defect_probability >= 0.66 else ("Medium" if defect_probability >= 0.33 else "Low")
    n1 = sum(y)
    return {
        "defect_probability": defect_probability, "risk_level": level,
        "feature_importances": importances,
        "class_counts": {"No defects (0)": len(y) - n1, "Defects (1)": n1},
        "class_share_percent": round(n1 / len(y) * 100, 1),
        "holdout_accuracy": holdout, "n_train": len(X_tr), "n_test": len(X_te),
        "note": "Probability estimate from a model trained on SYNTHETIC data derived from documented "
                "rules; not a guaranteed outcome. Replace with real historical defect data for "
                "production-grade accuracy.",
    }
