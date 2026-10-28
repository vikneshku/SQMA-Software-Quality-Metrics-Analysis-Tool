# SQMA-Software-Quality-Metrics-Analysis-Tool
SQMA is a Flask web app that checks software health from source code (Python, Java, JS, C, C++) and bug tracking. It measures complexity, maintainability and security, computes defect density, escape rate and release readiness, and adds statistics, ML risk prediction, alerts, a REST API and an offline AI assistant.


SQMA – Software Quality & Metrics Analysis Tool is a web application that checks the health of a software project from two sides: its source code and its bug tracker. Instead of judging quality by feel, it measures it with standard, well-known formulas and explains every number it shows.

Upload a whole project folder (Python, Java, JavaScript, C or C++) and SQMA analyses every file. It skips junk such as virtual environments and binary files, then measures size, cyclomatic complexity, maintainability and security problems. Each file gets a risk colour, and a Code Issues page lists dangerous patterns, long functions and missing documentation. One click turns an issue into a tracked bug.

The built-in bug tracker records severity, priority, assignee, release, OWASP category and CVSS score. From these it calculates defect density, escape rate, open versus closed ratio and the age of open bugs. Every release receives a Red, Yellow or Green readiness light with plain-language reasons, so teams can make a fair go or no-go decision.

SQMA also provides statistical analysis: control chart with selectable sigma and variance type, box plot, histogram, correlation, Welch and one-sample t-tests, and chi-square tests. Prediction models include an explainable decision tree, a random forest for defect probability and a step-by-step Bayesian risk model. Automatic alerts warn about aging bugs, a growing backlog, critical security bugs and releases that are not ready.

Results appear on a dashboard with a one-line project verdict, the riskiest files, and a folder-by-folder comparison. Every analysis page can show the whole project or a single file. A printable report shows the rule, formula, working and result for each metric.

Extra features include user roles (Admin, Developer, Tester), a REST API with token authentication, and an AI assistant. The assistant answers questions from real project data offline, and can also use a free Google Gemini key for deeper answers.

Built with Python, Flask, SQLAlchemy, SQLite, scikit-learn, SciPy, Bootstrap and Chart.js. It runs locally in the browser, works offline, and was designed for students, developers, testers and project managers who want clear, explainable software quality measurement.
