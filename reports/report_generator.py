"""
reports/report_generator.py
Report Generation. Builds the data used by report.html, covering all sections:
1. Project Info 2. Size 3. Complexity 4. Defects 5. Security
6. Maintainability 7. Statistics 8. Risk 9. Prediction 10. Recommendations
plus a worked calculation (formula -> numbers substituted -> result -> rule -> code
location) for every metric, so each number in the report can be explained.
"""
import math


def build_recommendations(quality: dict, complexity: dict, security_counts: dict,
                          maintainability: dict, defect_density_value: float) -> list:
    """Rule-based tips. They stay visible even when the AI recommendations (Phase 3) are available."""
    recs = []
    if quality.get("quality_score", 100) < 60:
        recs.append("Overall quality score is below target - prioritize the lowest-scoring component first.")
    if complexity.get("average_complexity", 0) > 10:
        recs.append("Average cyclomatic complexity is high - refactor the most complex functions listed in the Complexity section.")
    if security_counts.get("High", 0) > 0:
        recs.append("High-severity security findings exist - address these before release.")
    if maintainability.get("mi_score", 100) < 40:
        recs.append("Maintainability index is low (below 40) - consider reducing function size and complexity, and improving documentation.")
    if defect_density_value > 5:
        recs.append("Defect density is elevated - increase code review and testing coverage on affected modules.")
    if not recs:
        recs.append("No critical issues detected. Continue monitoring trends via the Control Chart and Dashboard.")
    return recs


def build_report(project, size, complexity, defect_stats, security_counts,
                 maintainability, statistics_summary, risk, prediction, quality) -> dict:
    recommendations = build_recommendations(quality, complexity, security_counts,
                                            maintainability, defect_stats.get("defect_density", 0))
    return {
        "project": project, "size": size, "complexity": complexity, "defects": defect_stats,
        "security_counts": security_counts, "maintainability": maintainability,
        "statistics": statistics_summary, "risk": risk, "prediction": prediction,
        "quality": quality, "recommendations": recommendations,
    }


def _c(group, title, formula, working, result, rule, code):
    return {"group": group, "title": title, "formula": formula, "working": working,
            "result": result, "rule": rule, "code": code}


def build_calculations(c: dict) -> list:
    """c = context dict prepared by app.report_page. Returns a list of worked calculations."""
    out = []
    ds, size, loc = c["defect_stats"], c["size"], c["loc"]

    # ---------------- Defects ----------------
    out.append(_c("Defect metrics", "Defect Density",
        "Defect Density = Number of bugs / (LOC / 1000)",
        f"{c['bugs_n']} bugs / ({loc} / 1000) = {c['dd']}",
        f"{c['dd']} defects per KLOC",
        "Lower is better. Feeds the Defects part of the Quality Score (100 - 5 x density) and the Alerts (>4 warning, >8 critical).",
        "metrics/defect_metrics.py -> defect_density()"))
    out.append(_c("Defect metrics", "MTTR (Mean Time To Repair)",
        "MTTR = sum(resolved_at - created_at) / number of resolved bugs   (in hours)",
        f"{ds['resolved_hours_total']} h / {ds['resolved_count']} resolved bug(s) = {ds['mttr_hours']} h" if ds['resolved_count'] else "No bug has been resolved yet, so MTTR is 0.",
        f"{ds['mttr_hours']} hours",
        "Only bugs that have a resolved date are counted. Shorter repair time is better.",
        "metrics/defect_metrics.py -> mttr_hours()"))
    out.append(_c("Defect metrics", "Reopen Rate",
        "Reopen Rate = (bugs reopened at least once / total bugs) x 100",
        f"({ds['reopened_count']} / {c['bugs_n']}) x 100 = {ds['reopen_rate']}%" if c['bugs_n'] else "No bugs logged, so the rate is 0%.",
        f"{ds['reopen_rate']} %",
        "A high value means fixes are not holding. Used as an input of the Decision Tree and Defect Prediction.",
        "metrics/defect_metrics.py -> reopen_rate()"))
    out.append(_c("Defect metrics", "Escape Rate (linked to releases)",
        "Escape Rate = (bugs with Found in = Production / total bugs) x 100   (per release and for the whole project)",
        f"({ds['escaped_count']} / {c['bugs_n']}) x 100 = {ds['escape_rate']}%" if c['bugs_n'] else "No bugs logged, so the rate is 0%.",
        f"{ds['escape_rate']} %",
        "Shows how many defects testing failed to catch before release. Each bug has a 'Found in' field (Testing or Production); with zero bugs the rate is 0.",
        "metrics/defect_metrics.py -> escape_rate(); metrics/release_metrics.py"))
    out.append(_c("Defect metrics", "Open vs Closed ratio",
        "Open = Open + In Progress + Reopened;  Closed = Resolved + Closed;  % open = open / (open + closed) x 100",
        f"{ds['open_count']} open : {ds['closed_count']} closed  ->  {ds['open_count']} / {ds['open_count'] + ds['closed_count']} x 100 = {ds['percent_open']}% open" if c['bugs_n'] else "No bugs logged yet.",
        f"{ds['open_count']} : {ds['closed_count']}  ({ds['percent_open']} % open)",
        "More open than closed bugs means the backlog is growing (Warning alert; Critical when open is more than double closed).",
        "metrics/defect_metrics.py -> open_closed()"))
    out.append(_c("Defect metrics", "Average age of OPEN bugs",
        "Bug age (days) = now - created_at;  Average = sum of ages of open bugs / number of open bugs",
        f"{ds['open_ages_total']} days / {ds['open_count']} open bug(s) = {ds['average_bug_age_days']} days" if ds['open_count'] else "No open bugs, so the average age is 0.",
        f"{ds['average_bug_age_days']} days;  {ds['old_bug_count']} open bug(s) older than 30 days",
        "Only open bugs are counted (resolved bugs no longer age). A bug open for more than 30 days raises an Aging alert.",
        "metrics/defect_metrics.py -> average_bug_age_days(), old_bug_count()"))
    out.append(_c("Defect metrics", "Module risk score",
        "Risk score = sum(weight of OPEN bugs) + 0.5 x sum(weight of CLOSED bugs) + 0.5 x average CVSS;   weights: Low 1, Medium 2, High 3, Critical 5",
        "; ".join(f"{m}: {d['risk_score']} ({d['risk_level']})" for m, d in c['modules'].items()) or "No bugs logged yet.",
        "Levels: score <= 5 Low, <= 15 Medium, above 15 High",
        "Open bugs count fully, closed bugs half, and a high average CVSS raises the score. Shown (sortable) on the Dashboard.",
        "metrics/defect_metrics.py -> module_risk()"))
    out.append(_c("Defect metrics", "CVSS severity bands",
        "CVSS v3 style band of a bug's score (0.0 - 10.0)",
        "0.0 None;  0.1-3.9 Low;  4.0-6.9 Medium;  7.0-8.9 High;  9.0-10.0 Critical",
        "A bug with CVSS >= 7.0 counts as a High-or-above security bug",
        "Security bugs (OWASP category set) that are open and Critical/High severity or CVSS >= 7.0 raise a Critical alert.",
        "metrics/cvss.py -> cvss_band()"))
    rows_txt = "; ".join(f"{r['name']}: {r['readiness']['color']} ({r['open']} open of {r['total']}, escape {r['escape_rate']}%)"
                          for r in c['release_rows']) or "No releases defined yet."
    out.append(_c("Defect metrics", "Release readiness (traffic light)",
        "Red / Yellow / Green from the open bugs of ONE release (thresholds in config.READINESS)",
        rows_txt,
        "RED: any open Critical bug, OR 3+ open High bugs, OR an open security bug with CVSS >= 9.  "
        "YELLOW: any open High bug, OR open bugs exceed closed, OR an open bug older than 30 days.  GREEN: otherwise.",
        "A release that turns Red raises a Critical alert. The latest release is shown on the Dashboard and the Releases page.",
        "metrics/release_metrics.py -> release_readiness()"))

    # ---------------- Control chart ----------------
    ctrl = c["ctrl"]
    vt_txt = "sample (n - 1)" if c["variance"] == "sample" else "population (n)"
    if ctrl.get("error"):
        out.append(_c("Defect metrics", "Control Chart limits", "CL = mean;  UCL = mean + k x sigma;  LCL = max(0, mean - k x sigma)",
                      ctrl["error"], "Not available", "Needs bugs on at least 2 different days.", "stats_engine/control_chart.py"))
    else:
        k = ctrl["sigma_mult"]
        out.append(_c("Defect metrics", "Control Chart limits",
            f"CL = mean;   UCL = mean + {k} x sigma;   LCL = max(0, mean - {k} x sigma)    [options used: {k}-sigma, {vt_txt} standard deviation]",
            f"mean = {ctrl['mean']},  sigma = {ctrl['sigma']}  ->  UCL = {ctrl['mean']} + {k} x {ctrl['sigma']} = {ctrl['ucl']};  LCL = max(0, {ctrl['mean']} - {k} x {ctrl['sigma']}) = {ctrl['lcl']}",
            f"CL = {ctrl['center_line']}, UCL = {ctrl['ucl']}, LCL = {ctrl['lcl']};  {len(ctrl['out_of_control_points'])} point(s) outside",
            "A point above UCL or below LCL is 'out of control' (unusual variation). 3-sigma catches only very unusual points (about 99.7% of normal variation); 2-sigma is more sensitive but gives more false alarms.",
            "stats_engine/control_chart.py -> build_control_chart()"))
    ss = c["stats_summary"]
    out.append(_c("Statistics", "Variance and standard deviation (option used: " + c["variance"] + ")",
        "Sample: s^2 = sum(x - mean)^2 / (n - 1);   Population: sigma^2 = sum(x - mean)^2 / n;   std dev = square root of the variance",
        f"complexity values: n = {ss['count']}, mean = {ss['mean']}, variance = {ss['variance']}, std dev = {ss['std_dev']}  ({vt_txt})" if ss['count'] else "No functions analysed yet.",
        f"{ss['variance_type']} variance = {ss['variance']}",
        "Sample variance (n - 1) is used when the data is a sample of a bigger process (default for bug data); population variance (n) when you hold every value.",
        "stats_engine/descriptive.py -> describe()"))

    # ---------------- Complexity / size ----------------
    fn = len(c["cx_values"])
    cx_sum = sum(c["cx_values"])
    out.append(_c("Complexity", "Cyclomatic Complexity of a function",
        "V(G) = E - N + 2P   (counted as: 1 + number of decision points)",
        "Start at 1, then add 1 for every if / elif / for / while / except / assert / extra 'and'-'or' operand.",
        f"Most complex function = {c['analysis']['max_complexity']}",
        "Project bands: 1-5 Low, 6-10 Moderate, 11-20 High, 21+ Very High (project-defined, not a universal standard).",
        "analyzers/complexity_analyzer.py -> _ComplexityVisitor"))
    out.append(_c("Complexity", "Average Complexity",
        "Average = sum of all function complexities / number of functions",
        f"{cx_sum} / {fn} = {c['analysis']['avg_complexity']}" if fn else "No functions found yet.",
        f"{c['analysis']['avg_complexity']}",
        "Used by the Maintainability Index, Quality Score, Decision Tree, Defect Prediction and Bayesian risk.",
        "analysis_service.py -> run_full_code_analysis()"))
    out.append(_c("Size", "Comment ratio and average function size",
        "Comment ratio = comment lines / total lines x 100;   Avg function size = mean(function end line - start line + 1)",
        f"{size['comment_lines']} / {size['total_loc']} x 100 = {size['comment_ratio_percent']}%;   average function = {size['avg_function_size']} lines",
        f"{size['comment_ratio_percent']} %  |  {size['avg_function_size']} lines",
        "Total lines = blank + comment + logical lines. Counted by reading every uploaded .py file.",
        "analyzers/code_analyzer.py, metrics/size_metrics.py"))

    # ---------------- Maintainability ----------------
    mi = c["mi"]
    fm = c["analysis"]["file_maintainability"]
    if fm:
        sample = max(fm, key=lambda r: r["loc"])
        ex = (f"Example (largest file {sample['file']}): avg function = {sample['avg_function_loc']} lines, CC = {sample['avg_complexity']}, "
              f"HV = {sample['avg_function_loc']} x log2(12) = {round(sample['avg_function_loc'] * math.log2(12), 2)}  ->  MI = {sample['mi_score']}.   "
              f"Project MI = LOC-weighted average of {len(fm)} file MI(s) = {mi['mi_score']}")
        out.append(_c("Maintainability", "Maintainability Index (MI) - per file, LOC-weighted per project",
            "MI = max(0, min(100, (171 - 5.2 x ln(HV) - 0.23 x CC - 16.2 x ln(avgFnLOC)) x 100 / 171)),   HV = avgFnLOC x log2(12)",
            ex, f"{mi['mi_score']} -> {mi['band']}",
            "Bands (project-defined, calibrated): 55-100 highly maintainable, 40-54.9 moderate, below 40 difficult to maintain. "
            "Check values: avg function 20 lines & CC 4 = 58; 50 lines & CC 25 = 44; 100 lines & CC 30 = 34. HV is a documented approximation.",
            "metrics/maintainability.py -> maintainability_index(), project_maintainability()"))

    # ---------------- Quality score ----------------
    q = c["quality"]
    cp = q["components"]
    out.append(_c("Quality", "Overall Quality Score",
        "Quality = 0.30 x Maintainability + 0.25 x Complexity + 0.25 x Defects + 0.20 x Security",
        f"0.30 x {cp['maintainability']} + 0.25 x {cp['complexity']} + 0.25 x {cp['defects']} + 0.20 x {cp['security']} = {q['quality_score']}",
        f"{q['quality_score']} % -> {q['quality_level']}",
        "Each component is first converted to 0-100: Complexity = 100 - (avg - 1) x 100/29;  Defects = 100 - 5 x density;  Security = 100 - (15 x High + 7 x Medium + 2 x Low). "
        "Levels: 80+ Excellent, 60+ Good, 40+ Needs Improvement, else Poor.",
        "metrics/quality_metrics.py -> overall_quality_score()"))
    sc = c["sec"]["counts"]
    out.append(_c("Security", "Security component of the score",
        "Security score = 100 - (15 x High + 7 x Medium + 2 x Low findings)",
        f"100 - (15 x {sc['High']} + 7 x {sc['Medium']} + 2 x {sc['Low']}) = {cp['security']}",
        f"{cp['security']} / 100  ({c['n_sec']} finding(s))",
        "Findings come from 8 explicit rules: AST call checks (eval, exec, os.system, pickle.loads, subprocess shell=True) and regex line checks (hard-coded secrets, SQL string building).",
        "analyzers/security_analyzer.py"))

    # ---------------- Histogram / box plot / correlation ----------------
    h = c["hist"]
    if not h.get("error"):
        out.append(_c("Statistics", "Histogram (class intervals)",
            "k = ceil(1 + log2 n)  (Sturges' rule);   class width = ceil((max - min + 1) / k)",
            f"n = {h['n']}, min = {h['min']}, max = {h['max']}  ->  {h['bins']} bin(s) of width {h['width']}:  " +
            ", ".join(f"[{l}] = {n}" for l, n in zip(h['labels'], h['counts'])),
            f"{h['bins']} class intervals",
            "Every value falls into exactly one interval, so the bar heights add up to n.",
            "stats_engine/histogram.py -> build_histogram()"))
    b = c["box"]
    if not b.get("error"):
        out.append(_c("Statistics", "Box Plot (quartiles and outliers)",
            "IQR = Q3 - Q1;   fences = Q1 - 1.5 x IQR  and  Q3 + 1.5 x IQR",
            f"Q1 = {b['q1']}, median = {b['median']}, Q3 = {b['q3']}  ->  IQR = {b['iqr']};   lower fence = {b['lower_fence']}, upper fence = {b['upper_fence']}",
            f"{len(b['outliers'])} outlier(s)" + (f": {b['outliers']}" if b['outliers'] else ""),
            "Whiskers end at the smallest / largest value inside the fences; any value outside a fence is plotted as an outlier dot.",
            "stats_engine/boxplot.py -> build_boxplot()"))
    r = c["corr"]
    out.append(_c("Statistics", "Pearson Correlation (function size vs complexity)",
        "r = sum[(x - mean x)(y - mean y)] / sqrt( sum(x - mean x)^2 x sum(y - mean y)^2 )",
        f"computed over {r.get('n', 0)} function(s)  ->  r = {r['r']},  r squared = {r.get('r_squared', 0)}",
        f"r = {r['r']}  ({r['strength']}, {r.get('kind', 'zero')})",
        "|r| >= 0.7 strong, 0.4-0.69 moderate, 0.2-0.39 weak, below 0.2 negligible. The sign gives the direction. Correlation shows association, not cause.",
        "stats_engine/correlation.py -> pearson_correlation()"))

    # ---------------- Decision tree ----------------
    d = c["dtree"]
    path_txt = "  ->  ".join(f"{s['text']} value {s['value']} = {s['answer']}" for s in d["path_steps"])
    out.append(_c("Prediction", "Decision Tree path for this project",
        "At each node the tree asks 'feature <= threshold?'; Yes goes left, No goes right, until a leaf gives the class.",
        path_txt or "(single leaf)",
        f"Predicted risk = {d['predicted_risk']}",
        f"scikit-learn DecisionTreeClassifier (max depth 4) trained on {d.get('n_training_samples', 0)} rule-derived synthetic samples. Feature importances show which input mattered most.",
        "prediction/decision_tree.py -> train_and_predict()"))

    # ---------------- Bayesian ----------------
    rk = c["risk"]
    ev = rk["evidence_used"]
    out.append(_c("Risk", "Bayesian Risk  P(Risk | Evidence)",
        "P(Risk | E1..E4) is proportional to P(Risk) x P(E1|Risk) x P(E2|Risk) x P(E3|Risk) x P(E4|Risk);  then normalise so the three values add to 1",
        "Evidence: " + ", ".join(f"{k.replace('_', ' ')} = {'Yes' if v else 'No'}" for k, v in ev.items()) +
        ".   Result: " + ", ".join(f"P({k}) = {v}" for k, v in rk["probabilities"].items()),
        f"Predicted risk = {rk['predicted_risk']}",
        "Evidence rules: complexity > 10, defect density > 3 per KLOC, any security finding, maintainability < 40. Priors and likelihoods are project-defined, documented estimates.",
        "bayesian/risk_model.py, prediction/risk_prediction.py"))
    p = c["prediction"]
    di = c["dt_inputs"]
    cc_ = p["class_counts"]
    out.append(_c("Prediction", "Defect Prediction (Random Forest)",
        "defect probability = share of the 80 trees in the forest that vote 'will have defects';  features: loc, complexity, defect_density, reopen_rate, security_issues",
        f"inputs: LOC {di['loc']}, complexity {di['complexity']}, defect density {c['dd']}, reopen rate {di['reopen_rate']}, security issues {c['n_sec']}.  "
        f"Training classes: {', '.join(f'{k} = {v}' for k, v in cc_.items())} ({p['class_share_percent']}% with defects); hold-out accuracy = {round(p['holdout_accuracy'] * 100, 1)}%",
        f"{round(p['defect_probability'] * 100, 1)} % -> {p['risk_level']} risk",
        "Risk level: >= 66% High, 33-65% Medium, below 33% Low. Trained on SYNTHETIC data with stratified generation and class_weight='balanced'; the duplicate module_size feature was removed. A probability estimate, not a guaranteed outcome.",
        "prediction/defect_prediction.py -> predict_defect_risk()"))
    return out
