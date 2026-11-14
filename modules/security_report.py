"""Text and HTML report builders for security scan results.

The building blocks (ordered, text_rows, html_section, html_page, score_header_html) are
shared with modules.threat_report.
"""
import getpass
import html
import os
import platform
from datetime import datetime

from modules.security_checks import (CATEGORIES, CHECKS, SEVERITIES, STATUS_ORDER,
                                     risk_summary)

ICON = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "UNKNOWN": "?", "INFO": "i"}
LEVEL_COLOR = {"CLEAN": "#1e8449", "LOW": "#2874a6", "MEDIUM": "#b9770e",
               "HIGH": "#c0392b", "CRITICAL": "#7b241c"}
STATUS_COLOR = {"PASS": "#1e8449", "FAIL": "#c0392b", "WARN": "#b9770e",
                "UNKNOWN": "#7f8c8d", "INFO": "#2874a6"}
SEV_COLOR = {"HIGH": "#c0392b", "MEDIUM": "#b9770e", "LOW": "#7f8c8d"}

_e = html.escape


def machine_meta():
    return {
        "computer": os.environ.get("COMPUTERNAME") or platform.node(),
        "domain": os.environ.get("USERDNSDOMAIN") or os.environ.get("USERDOMAIN") or "",
        "user": getpass.getuser(),
        "os": f"{platform.system()} {platform.release()} (build {platform.version()})",
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def ordered(checks, results):
    """Failures first, then warnings/unknown/info/pass; within that by severity."""
    return sorted(
        checks,
        key=lambda c: (STATUS_ORDER.get(results.get(c["id"], ("UNKNOWN",))[0], 2),
                       SEVERITIES.index(c["severity"])))


def ordered_checks(category, results):
    return ordered([c for c in CHECKS if c["category"] == category], results)


def impact_note(check):
    return ("If fixed", check.get("impact"))


def text_rows(checks, results, fixed=(), note=impact_note):
    out = []
    for check in ordered(checks, results):
        status, detail = results.get(check["id"], ("UNKNOWN", ""))
        tag = "  [FIXED THIS SESSION]" if check["id"] in fixed else ""
        out.append(f"  {ICON.get(status, '-')} {status:<7} {check['severity']:<6} {check['name']}{tag}")
        if detail:
            out.append(f"        {detail}")
        if status in ("FAIL", "WARN"):
            out.append(f"        Why: {check['description']}")
            label, text = note(check)
            if text:
                out.append(f"        {label}: {text}")
    return out


def counts_line(c, total):
    line = f"{c['FAIL']} FAIL   {c['WARN']} WARN   {c['PASS']} PASS"
    if c.get("INFO"):
        line += f"   {c['INFO']} INFO"
    if c.get("UNKNOWN"):
        line += f"   {c['UNKNOWN']} UNKNOWN"
    return line + f"   ({total} checks)"


def text_header(title, meta):
    return [
        f"IT Provisioning Tool — {title}",
        f"Machine:   {meta['computer']}" + (f"  ({meta['domain']})" if meta["domain"] else ""),
        f"OS:        {meta['os']}",
        f"Run by:    {meta['user']}",
        f"Generated: {meta['generated']}",
        "=" * 64,
    ]


def build_text(results, fixed=(), meta=None):
    meta = meta or machine_meta()
    s = risk_summary(results)
    out = text_header("Security Scan Report", meta) + [
        f"RISK LEVEL: {s['level']}    Security score: {s['score']}/100",
        counts_line(s["counts"], len(CHECKS)),
        "=" * 64,
    ]
    for cat in CATEGORIES:
        out += ["", f"[ {cat.upper()} ]"]
        out += text_rows([c for c in CHECKS if c["category"] == cat], results, fixed)
    return "\n".join(out) + "\n"


# ── HTML ──────────────────────────────────────────────────────────────

CSS = """
  body { font: 14px/1.45 "Segoe UI", system-ui, sans-serif; margin: 0; background: #f4f5f7; color: #1c1f23; }
  main { max-width: 980px; margin: 0 auto; padding: 24px 16px 48px; }
  header { background: #fff; border-radius: 10px; padding: 20px 22px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  h1 { margin: 0 0 4px; font-size: 22px; }
  .meta { color: #5f6670; font-size: 13px; }
  .score { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-top: 16px; }
  .level { color: #fff; font-weight: 700; padding: 8px 16px; border-radius: 6px; font-size: 16px; }
  .num { font-size: 28px; font-weight: 700; } .num small { font-size: 14px; color: #5f6670; font-weight: 400; }
  .pill { padding: 3px 10px; border-radius: 12px; color: #fff; font-weight: 600; font-size: 12px; }
  .verdicts { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-top: 16px; }
  .verdict { border: 1px solid #e3e5e8; border-left: 5px solid; border-radius: 6px; padding: 10px 14px; }
  .verdict b { display: block; font-size: 13px; color: #5f6670; font-weight: 600; }
  .verdict span { font-size: 16px; font-weight: 700; }
  h1.part { font-size: 19px; margin: 30px 0 0; }
  section { background: #fff; border-radius: 10px; margin-top: 14px; overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  h2 { margin: 0; padding: 12px 18px; font-size: 16px; background: #eceef1; }
  .cat-sum { font-weight: 400; color: #5f6670; font-size: 13px; margin-left: 8px; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  td { padding: 10px 12px; border-top: 1px solid #eceef1; vertical-align: top; }
  td:first-child { width: 92px; padding-left: 18px; } td:nth-child(2) { width: 70px; }
  .status { color: #fff; font-weight: 700; font-size: 11px; padding: 3px 8px; border-radius: 4px; white-space: nowrap; }
  .sev { font-size: 10px; font-weight: 700; border: 1px solid; border-radius: 3px; padding: 1px 5px; }
  .name { font-weight: 600; } .detail { color: #2c3036; overflow-wrap: anywhere; }
  .why, .impact { color: #5f6670; font-size: 12.5px; margin-top: 4px; }
  .fixed { background: #d5f5e3; color: #1e8449; font-size: 11px; padding: 1px 6px; border-radius: 3px; font-weight: 600; }
  tr.st-pass .detail { color: #5f6670; }
  footer { color: #8a9099; font-size: 12px; margin-top: 18px; text-align: center; }
"""


def _summary_text(checks, results):
    statuses = [results.get(c["id"], ("UNKNOWN",))[0] for c in checks]
    parts = []
    for st, word in (("FAIL", "failed"), ("WARN", "warning"), ("INFO", "to review")):
        n = statuses.count(st)
        if n:
            parts.append(f"{n} {word}{'s' if st == 'WARN' and n != 1 else ''}")
    return " · ".join(parts) or "all passed"


def html_section(title, checks, results, fixed=(), note=impact_note):
    rows = []
    for ch in ordered(checks, results):
        status, detail = results.get(ch["id"], ("UNKNOWN", ""))
        extra = ""
        if status in ("FAIL", "WARN"):
            extra = f'<div class="why">{_e(ch["description"])}</div>'
            label, text = note(ch)
            if text:
                extra += f'<div class="impact"><b>{_e(label)}:</b> {_e(text)}</div>'
        fixed_tag = '<span class="fixed">fixed this session</span>' if ch["id"] in fixed else ""
        sev_c = SEV_COLOR[ch["severity"]]
        rows.append(
            f'<tr class="st-{status.lower()}">'
            f'<td><span class="status" style="background:{STATUS_COLOR.get(status, "#7f8c8d")}">'
            f'{ICON.get(status, "?")} {status}</span></td>'
            f'<td><span class="sev" style="color:{sev_c};border-color:{sev_c}">{ch["severity"]}</span></td>'
            f'<td><div class="name">{_e(ch["name"])} {fixed_tag}</div>'
            f'<div class="detail">{_e(detail) if detail else ""}</div>{extra}</td></tr>')
    return (f'<section><h2>{_e(title)} <span class="cat-sum">{_summary_text(checks, results)}'
            f'</span></h2><div class="table-wrap"><table>{"".join(rows)}</table></div></section>')


def pills_html(c):
    pills = [("FAIL", "failed"), ("WARN", "warnings"), ("PASS", "passed"),
             ("INFO", "to review"), ("UNKNOWN", "unknown")]
    return "".join(
        f'<span class="pill" style="background:{STATUS_COLOR[k]}">{c[k]} {word}</span>'
        for k, word in pills if c.get(k) or k in ("FAIL", "WARN", "PASS"))


def html_page(title, meta, header_extra, body, total):
    domain = f" ({_e(meta['domain'])})" if meta["domain"] else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)} — {_e(meta['computer'])}</title>
<style>{CSS}</style></head>
<body><main>
<header>
  <h1>{_e(title)} — {_e(meta['computer'])}{domain}</h1>
  <div class="meta">{_e(meta['os'])} · run by {_e(meta['user'])} · {_e(meta['generated'])}</div>
  {header_extra}
</header>
{body}
<footer>{total} checks · IT Provisioning Tool</footer>
</main></body></html>
"""


def build_html(results, fixed=(), meta=None):
    meta = meta or machine_meta()
    s = risk_summary(results)
    header = (f'<div class="score"><span class="level" style="background:{LEVEL_COLOR[s["level"]]}">'
              f'{s["level"]}</span><span class="num">{s["score"]}<small>/100 security score</small>'
              f'</span>{pills_html(s["counts"])}</div>')
    body = "".join(html_section(cat, [c for c in CHECKS if c["category"] == cat], results, fixed)
                   for cat in CATEGORIES)
    return html_page("Security Report", meta, header, body, len(CHECKS))
