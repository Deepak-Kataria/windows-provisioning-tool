"""Text and HTML report builders for security scan results."""
import getpass
import html
import os
import platform
from datetime import datetime

from modules.security_checks import (CATEGORIES, CHECKS, SEVERITIES, STATUS_ORDER,
                                     risk_summary)

_ICON = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "UNKNOWN": "?"}


def machine_meta():
    return {
        "computer": os.environ.get("COMPUTERNAME") or platform.node(),
        "domain": os.environ.get("USERDNSDOMAIN") or os.environ.get("USERDOMAIN") or "",
        "user": getpass.getuser(),
        "os": f"{platform.system()} {platform.release()} (build {platform.version()})",
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def ordered_checks(category, results):
    """Checks of a category: failures first, then by severity."""
    return sorted(
        (c for c in CHECKS if c["category"] == category),
        key=lambda c: (STATUS_ORDER.get(results.get(c["id"], ("UNKNOWN",))[0], 2),
                       SEVERITIES.index(c["severity"])))


def build_text(results, fixed=(), meta=None):
    meta = meta or machine_meta()
    s = risk_summary(results)
    c = s["counts"]
    out = [
        "IT Provisioning Tool — Security Scan Report",
        f"Machine:   {meta['computer']}" + (f"  ({meta['domain']})" if meta["domain"] else ""),
        f"OS:        {meta['os']}",
        f"Run by:    {meta['user']}",
        f"Generated: {meta['generated']}",
        "=" * 64,
        f"RISK LEVEL: {s['level']}    Security score: {s['score']}/100",
        f"{c['FAIL']} FAIL   {c['WARN']} WARN   {c['PASS']} PASS   {c['UNKNOWN']} UNKNOWN"
        f"   ({len(CHECKS)} checks)",
        "=" * 64,
    ]
    for cat in CATEGORIES:
        out += ["", f"[ {cat.upper()} ]"]
        for check in ordered_checks(cat, results):
            status, detail = results.get(check["id"], ("UNKNOWN", ""))
            tag = "  [FIXED THIS SESSION]" if check["id"] in fixed else ""
            out.append(f"  {_ICON.get(status, '-')} {status:<7} {check['severity']:<6} {check['name']}{tag}")
            if detail:
                out.append(f"        {detail}")
            if status in ("FAIL", "WARN"):
                out.append(f"        Why: {check['description']}")
                if check.get("impact"):
                    out.append(f"        If fixed: {check['impact']}")
    return "\n".join(out) + "\n"


_LEVEL_COLOR = {"CLEAN": "#1e8449", "LOW": "#2874a6", "MEDIUM": "#b9770e",
                "HIGH": "#c0392b", "CRITICAL": "#7b241c"}
_STATUS_COLOR = {"PASS": "#1e8449", "FAIL": "#c0392b", "WARN": "#b9770e", "UNKNOWN": "#7f8c8d"}
_SEV_COLOR = {"HIGH": "#c0392b", "MEDIUM": "#b9770e", "LOW": "#7f8c8d"}


def build_html(results, fixed=(), meta=None):
    meta = meta or machine_meta()
    s = risk_summary(results)
    c = s["counts"]
    e = html.escape

    sections = []
    for cat in CATEGORIES:
        checks = ordered_checks(cat, results)
        n_fail = sum(1 for ch in checks if results.get(ch["id"], ("",))[0] == "FAIL")
        n_warn = sum(1 for ch in checks if results.get(ch["id"], ("",))[0] == "WARN")
        rows = []
        for ch in checks:
            status, detail = results.get(ch["id"], ("UNKNOWN", ""))
            extra = ""
            if status in ("FAIL", "WARN"):
                extra = f'<div class="why">{e(ch["description"])}</div>'
                if ch.get("impact"):
                    extra += f'<div class="impact"><b>If fixed:</b> {e(ch["impact"])}</div>'
            fixed_tag = '<span class="fixed">fixed this session</span>' if ch["id"] in fixed else ""
            rows.append(
                f'<tr class="st-{status.lower()}">'
                f'<td><span class="status" style="background:{_STATUS_COLOR.get(status, "#7f8c8d")}">'
                f'{_ICON.get(status, "?")} {status}</span></td>'
                f'<td><span class="sev" style="color:{_SEV_COLOR[ch["severity"]]};'
                f'border-color:{_SEV_COLOR[ch["severity"]]}">{ch["severity"]}</span></td>'
                f'<td><div class="name">{e(ch["name"])} {fixed_tag}</div>'
                f'<div class="detail">{e(detail) if detail else ""}</div>{extra}</td></tr>')
        summary = []
        if n_fail:
            summary.append(f"{n_fail} failed")
        if n_warn:
            summary.append(f"{n_warn} warning{'s' if n_warn != 1 else ''}")
        sections.append(
            f'<section><h2>{e(cat)} <span class="cat-sum">'
            f'{" · ".join(summary) or "all passed"}</span></h2>'
            f'<table>{"".join(rows)}</table></section>')

    domain = f" ({e(meta['domain'])})" if meta["domain"] else ""
    unknown_pill = (f'<span class="pill" style="background:{_STATUS_COLOR["UNKNOWN"]}">'
                    f'{c["UNKNOWN"]} unknown</span>') if c["UNKNOWN"] else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Security Report — {e(meta['computer'])}</title>
<style>
  body {{ font: 14px/1.45 "Segoe UI", system-ui, sans-serif; margin: 0; background: #f4f5f7; color: #1c1f23; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 24px 16px 48px; }}
  header {{ background: #fff; border-radius: 10px; padding: 20px 22px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  h1 {{ margin: 0 0 4px; font-size: 22px; }}
  .meta {{ color: #5f6670; font-size: 13px; }}
  .score {{ display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-top: 16px; }}
  .level {{ color: #fff; font-weight: 700; padding: 8px 16px; border-radius: 6px; font-size: 16px;
            background: {_LEVEL_COLOR[s['level']]}; }}
  .num {{ font-size: 28px; font-weight: 700; }} .num small {{ font-size: 14px; color: #5f6670; font-weight: 400; }}
  .pill {{ padding: 3px 10px; border-radius: 12px; color: #fff; font-weight: 600; font-size: 12px; }}
  section {{ background: #fff; border-radius: 10px; margin-top: 18px; overflow: hidden;
             box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  h2 {{ margin: 0; padding: 12px 18px; font-size: 16px; background: #eceef1; }}
  .cat-sum {{ font-weight: 400; color: #5f6670; font-size: 13px; margin-left: 8px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ padding: 10px 12px; border-top: 1px solid #eceef1; vertical-align: top; }}
  td:first-child {{ width: 92px; padding-left: 18px; }} td:nth-child(2) {{ width: 70px; }}
  .status {{ color: #fff; font-weight: 700; font-size: 11px; padding: 3px 8px; border-radius: 4px; white-space: nowrap; }}
  .sev {{ font-size: 10px; font-weight: 700; border: 1px solid; border-radius: 3px; padding: 1px 5px; }}
  .name {{ font-weight: 600; }} .detail {{ color: #2c3036; }}
  .why, .impact {{ color: #5f6670; font-size: 12.5px; margin-top: 4px; }}
  .fixed {{ background: #d5f5e3; color: #1e8449; font-size: 11px; padding: 1px 6px; border-radius: 3px; font-weight: 600; }}
  tr.st-pass .detail {{ color: #5f6670; }}
  footer {{ color: #8a9099; font-size: 12px; margin-top: 18px; text-align: center; }}
</style></head>
<body><main>
<header>
  <h1>Security Report — {e(meta['computer'])}{domain}</h1>
  <div class="meta">{e(meta['os'])} · run by {e(meta['user'])} · {e(meta['generated'])}</div>
  <div class="score">
    <span class="level">{s['level']}</span>
    <span class="num">{s['score']}<small>/100 security score</small></span>
    <span class="pill" style="background:{_STATUS_COLOR['FAIL']}">{c['FAIL']} failed</span>
    <span class="pill" style="background:{_STATUS_COLOR['WARN']}">{c['WARN']} warnings</span>
    <span class="pill" style="background:{_STATUS_COLOR['PASS']}">{c['PASS']} passed</span>
    {unknown_pill}
  </div>
</header>
{''.join(sections)}
<footer>{len(CHECKS)} checks · IT Provisioning Tool</footer>
</main></body></html>
"""
