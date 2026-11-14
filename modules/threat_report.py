"""System Compromise & Threat Report: scoring and TXT/HTML builders.

Two parts: "Signs of Compromise" (modules.threat_checks) and "Vulnerability Exposure"
(every Security tab check from modules.security_checks).
"""
from modules import security_checks as sc
from modules import security_report as sr
from modules.threat_checks import COMPROMISE_CHECKS, compromise_level

ALL_CHECKS = COMPROMISE_CHECKS + sc.CHECKS
ALL_BY_ID = {c["id"]: c for c in ALL_CHECKS}
assert len(ALL_BY_ID) == len(ALL_CHECKS), "duplicate check id between threat and security checks"

_VERDICT = {
    "CLEAN":    "No signs of compromise found",
    "LOW":      "Minor items to review",
    "MEDIUM":   "Suspicious activity to review",
    "HIGH":     "Likely compromise indicators",
    "CRITICAL": "Strong signs of compromise",
}


def action_note(check):
    return ("Recommended action", check.get("action"))


def exposure_note(check):
    impact = check.get("impact")
    if check.get("fix_label") and sc.is_auto_fixable(check):
        return ("Fix", f"Security tab > {check['fix_label']}. {impact or ''}".strip())
    return ("If fixed", impact)


def threat_summary(results):
    comp = compromise_level(results)
    exp = sc.risk_summary(results, sc.CHECKS)
    overall = max(comp, exp["level"], key=sc.RISK_LEVELS.index)
    comp_counts = sc.risk_summary(results, COMPROMISE_CHECKS)["counts"]
    return {
        "overall": overall,
        "compromise_level": comp,
        "compromise_verdict": _VERDICT[comp],
        "compromise_counts": comp_counts,
        "exposure": exp,
    }


def build_text(results, meta=None):
    meta = meta or sr.machine_meta()
    t = threat_summary(results)
    exp = t["exposure"]
    out = sr.text_header("System Compromise & Threat Report", meta) + [
        f"OVERALL RISK: {t['overall']}",
        f"Signs of compromise:    {t['compromise_level']} — {t['compromise_verdict']}",
        f"Vulnerability exposure: {exp['level']} — security score {exp['score']}/100",
        "=" * 64,
        "",
        "SIGNS OF COMPROMISE (was it hacked?)",
        "  " + sr.counts_line(t["compromise_counts"], len(COMPROMISE_CHECKS)),
    ]
    out += sr.text_rows(COMPROMISE_CHECKS, results, note=action_note)
    out += ["", "=" * 64, "", "VULNERABILITY EXPOSURE (can it be hacked?)",
            "  " + sr.counts_line(exp["counts"], len(sc.CHECKS))]
    for cat in sc.CATEGORIES:
        out += ["", f"[ {cat.upper()} ]"]
        out += sr.text_rows([c for c in sc.CHECKS if c["category"] == cat], results,
                            note=exposure_note)
    return "\n".join(out) + "\n"


def build_html(results, meta=None):
    meta = meta or sr.machine_meta()
    t = threat_summary(results)
    exp = t["exposure"]
    lc = sr.LEVEL_COLOR
    header = (
        f'<div class="score"><span class="level" style="background:{lc[t["overall"]]}">'
        f'OVERALL: {t["overall"]}</span></div>'
        f'<div class="verdicts">'
        f'<div class="verdict" style="border-left-color:{lc[t["compromise_level"]]}">'
        f'<b>Signs of compromise</b><span>{t["compromise_level"]}</span> — {sr._e(t["compromise_verdict"])}'
        f'</div>'
        f'<div class="verdict" style="border-left-color:{lc[exp["level"]]}">'
        f'<b>Vulnerability exposure</b><span>{exp["level"]}</span> — security score {exp["score"]}/100'
        f'</div></div>')
    body = (
        '<h1 class="part">Signs of Compromise <span class="cat-sum">was it hacked?</span></h1>'
        + sr.html_section("Compromise indicators", COMPROMISE_CHECKS, results, note=action_note)
        + '<h1 class="part">Vulnerability Exposure <span class="cat-sum">can it be hacked?</span></h1>'
        + "".join(sr.html_section(cat, [c for c in sc.CHECKS if c["category"] == cat], results,
                                  note=exposure_note)
                  for cat in sc.CATEGORIES))
    return sr.html_page("Threat Report", meta, header, body, len(ALL_CHECKS))
