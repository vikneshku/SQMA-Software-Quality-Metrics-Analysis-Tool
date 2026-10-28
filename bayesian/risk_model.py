"""
bayesian/risk_model.py
Bayesian Risk Prediction (Feature 8) - P(Risk | Evidence).

Implements Naive Bayes reasoning manually (documented, transparent formula)
rather than a black-box library, so every probability can be explained
step by step in a viva:

    P(Risk=High | E1,E2,...) proportional to
        P(Risk=High) * P(E1|Risk=High) * P(E2|Risk=High) * ...

Evidence variables (each True/False, derived from thresholds you can see
and adjust):
    high_complexity   : average cyclomatic complexity > 10
    has_defect_history: defect density > 3 per KLOC
    security_findings : one or more security issues found
    low_maintainability: maintainability index < 40

Prior and likelihood tables below are DOCUMENTED, PROJECT-DEFINED
estimates (not derived from a large external dataset) — presented
honestly as such.
"""

PRIOR = {"High": 0.25, "Medium": 0.35, "Low": 0.40}

# P(evidence=True | Risk class)
LIKELIHOOD_TRUE = {
    "high_complexity":    {"High": 0.75, "Medium": 0.40, "Low": 0.10},
    "has_defect_history": {"High": 0.70, "Medium": 0.45, "Low": 0.15},
    "security_findings":  {"High": 0.65, "Medium": 0.30, "Low": 0.05},
    "low_maintainability": {"High": 0.60, "Medium": 0.35, "Low": 0.10},
}


def compute_risk_probability(high_complexity: bool, has_defect_history: bool,
                              security_findings: bool, low_maintainability: bool) -> dict:
    evidence = {
        "high_complexity": high_complexity,
        "has_defect_history": has_defect_history,
        "security_findings": security_findings,
        "low_maintainability": low_maintainability,
    }

    raw = {}
    steps = {}
    for risk_class, prior in PRIOR.items():
        p = prior
        step_list = [f"P(Risk={risk_class}) = {prior}"]
        for ev_name, ev_value in evidence.items():
            p_true = LIKELIHOOD_TRUE[ev_name][risk_class]
            p_ev = p_true if ev_value else (1 - p_true)
            p *= p_ev
            step_list.append(
                f"P({ev_name}={ev_value}|Risk={risk_class}) = {round(p_ev, 3)}"
            )
        raw[risk_class] = p
        steps[risk_class] = step_list

    total = sum(raw.values())
    normalized = {k: round(v / total, 3) if total > 0 else 0 for k, v in raw.items()}

    predicted_class = max(normalized, key=normalized.get)

    return {
        "probabilities": normalized,
        "predicted_risk": predicted_class,
        "evidence_used": evidence,
        "explanation_steps": steps,
        "note": "Priors and likelihoods are project-defined estimates, documented "
                "above, and should be validated/calibrated against your dataset.",
    }
