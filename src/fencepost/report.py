"""Render the ledger as something a human will actually read."""

from __future__ import annotations

import html
from .models import Finding, Kind, Ledger, Severity

KIND_LABEL = {
    Kind.PYTHON_REQUIRES: "版本门槛",
    Kind.DEPENDENCY: "依赖声明",
    Kind.COMMAND: "文档命令",
    Kind.ENV_VAR: "凭据读取",
}
KIND_EN = {
    Kind.PYTHON_REQUIRES: "python_requires",
    Kind.DEPENDENCY: "dependency",
    Kind.COMMAND: "command",
    Kind.ENV_VAR: "env_var",
}
SEVERITY_LABEL = {Severity.HIGH: "高", Severity.MEDIUM: "中", Severity.LOW: "低"}
SEVERITY_EN = {Severity.HIGH: "high", Severity.MEDIUM: "medium", Severity.LOW: "low"}


def drifting(ledger: Ledger) -> list[Finding]:
    return [f for f in ledger.findings if f.is_drift and not f.rebutted]


def rebutted(ledger: Ledger) -> list[Finding]:
    return [f for f in ledger.findings if f.is_drift and f.rebutted]


def render_markdown(ledger: Ledger, title: str) -> str:
    run = ledger.run
    lines: list[str] = []
    lines.append(f"# Fencepost 审计单 · {title}")
    lines.append("")
    lines.append(
        f"- 模式：`{run.mode}`｜模型：`{run.model or '—'}`｜耗时：{run.duration_seconds}s"
        f"｜模型调用：{run.model_calls} 次（失败 {run.model_failures}）"
    )
    lines.append(
        f"- 承诺提出 {run.claims_offered} 条，逐字核对通过 {run.claims_offered - run.claims_dropped} 条，"
        f"被逐字核对拒绝 **{run.claims_dropped}** 条"
    )
    lines.append(f"- 判定漂移 **{ledger.count()}** 条"
                 f"（高 {ledger.count(Severity.HIGH)} / 中 {ledger.count(Severity.MEDIUM)}"
                 f" / 低 {ledger.count(Severity.LOW)}）｜被驳回 {len(rebutted(ledger))} 条")
    lines.append("")

    found = drifting(ledger)
    lines.append("## 漂移清单")
    lines.append("")
    if not found:
        lines.append("没有发现漂移。")
    else:
        lines.append("| # | 严重度 | 类型 | 承诺 | 实际 | 判词 |")
        lines.append("|---|---|---|---|---|---|")
        for index, finding in enumerate(found, start=1):
            promise = f"`{finding.claim.file}:{finding.claim.line}` {_inline(finding.claim.quote)}"
            actual = (
                f"`{finding.implementation.file}:{finding.implementation.line}` "
                f"{_inline(finding.implementation.snippet or finding.implementation.value)}"
                if finding.implementation
                else "**未找到对应实现**"
            )
            lines.append(
                f"| {index} | {SEVERITY_LABEL[finding.severity]} | {KIND_LABEL[finding.kind]} "
                f"| {promise} | {actual} | {_inline(finding.why)} |"
            )
    return "\n".join(lines) + "\n"


def _inline(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")[:180]


def render_html(ledger: Ledger, title: str) -> str:
    run = ledger.run
    found = drifting(ledger)
    lost = rebutted(ledger)
    high = ledger.count(Severity.HIGH)
    rows = "\n".join(_row(index, finding) for index, finding in enumerate(found, start=1))
    lost_rows = "\n".join(_lost_row(finding) for finding in lost)
    dropped_rows = "\n".join(
        f"<tr><td class=mono>{html.escape(item.get('file', ''))}</td>"
        f"<td class=mono>{html.escape(item.get('quote', ''))}</td>"
        f"<td>{html.escape(item.get('reason', ''))}</td></tr>"
        for item in ledger.dropped_quotes
    )

    if found:
        headline = f"{len(found)} 处承诺与实现不符，其中 {high} 处会让照着文档做的人踩空"
    else:
        headline = "承诺与实现一致：没有发现漂移"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fencepost 审计单 · {html.escape(title)}</title>
<style>
  :root {{
    --paper: #fbfaf7; --ink: #1b1a17; --soft: #6b665e; --rule: #ded9cf;
    --high: #8a2b06; --mid: #9a6a00; --low: #4c5a61; --tint: #f2eee6;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--paper); color: var(--ink);
    font-family: "Iowan Old Style", "Songti SC", "Source Han Serif SC", Georgia, serif;
    font-size: 15px; line-height: 1.65;
  }}
  .sheet {{ max-width: 1080px; margin: 0 auto; padding: 56px 40px 80px; }}
  .kicker {{ font-size: 11px; letter-spacing: .22em; text-transform: uppercase; color: var(--soft); }}
  h1 {{ font-size: 40px; line-height: 1.15; margin: 10px 0 6px; font-weight: 600; letter-spacing: -.01em; }}
  .headline {{ font-size: 19px; margin: 0 0 4px; color: #2c2a26; }}
  .meta {{ color: var(--soft); font-size: 13px; font-variant-numeric: tabular-nums; }}
  .meta code {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }}
  .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; margin: 34px 0 8px;
            border-top: 2px solid var(--ink); border-bottom: 1px solid var(--rule); }}
  .stat {{ padding: 16px 18px 14px 0; }}
  .stat + .stat {{ border-left: 1px solid var(--rule); padding-left: 22px; }}
  .stat b {{ display: block; font-size: 34px; font-weight: 600; font-variant-numeric: tabular-nums;
             line-height: 1.05; letter-spacing: -.02em; }}
  .stat span {{ font-size: 12px; color: var(--soft); letter-spacing: .04em; }}
  .stat.high b {{ color: var(--high); }}
  h2 {{ font-size: 15px; letter-spacing: .08em; text-transform: uppercase; color: var(--soft);
        margin: 44px 0 12px; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; font-size: 11px; letter-spacing: .1em; color: var(--soft);
        font-weight: 600; padding: 0 10px 8px 0; border-bottom: 1px solid var(--ink); }}
  td {{ vertical-align: top; padding: 14px 10px 14px 0; border-bottom: 1px solid var(--rule); }}
  td.n {{ color: var(--soft); font-variant-numeric: tabular-nums; width: 26px; }}
  .tag {{ display: inline-block; font-size: 11px; letter-spacing: .06em; padding: 2px 7px;
          border: 1px solid currentColor; border-radius: 2px; white-space: nowrap; }}
  .tag.high {{ color: var(--high); }}
  .tag.medium {{ color: var(--mid); }}
  .tag.low {{ color: var(--low); }}
  .kind {{ display: block; margin-top: 6px; font-size: 12px; color: var(--soft); }}
  .where {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 11.5px; color: var(--soft); }}
  .quote {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 12.5px;
            background: var(--tint); padding: 7px 9px; margin: 3px 0 0; white-space: pre-wrap;
            border-left: 2px solid var(--rule); }}
  .why {{ grid-column: 1 / -1; margin: 8px 0 0; color: #3a3733; font-size: 13.5px; }}
  .missing {{ color: var(--high); font-size: 13px; }}
  .quiet {{ color: var(--soft); font-size: 13px; }}
  .mono {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }}
  footer {{ margin-top: 52px; padding-top: 14px; border-top: 1px solid var(--rule);
            color: var(--soft); font-size: 12px; }}
  footer code {{ font-family: "SFMono-Regular", Consolas, monospace; }}
  @media print {{ body {{ background: #fff; }} .sheet {{ padding: 24px; }} }}
</style>
</head>
<body>
<div class="sheet">
  <div class="kicker">Fencepost · contract drift audit</div>
  <h1>{html.escape(title)}</h1>
  <p class="headline">{html.escape(headline)}</p>
  <p class="meta">
    {html.escape(run.mode)} 模式 ·
    模型 <code>{html.escape(run.model or "—")}</code> ·
    {run.duration_seconds}s ·
    {run.model_calls} 次模型调用（失败 {run.model_failures}）·
    {run.input_tokens:,} / {run.output_tokens:,} tokens ·
    会话 <code>{html.escape(run.session_id)}</code>
  </p>

  <div class="stats">
    <div class="stat"><b>{len(found)}</b><span>判定漂移</span></div>
    <div class="stat high"><b>{high}</b><span>高严重度</span></div>
    <div class="stat"><b>{run.claims_offered}</b><span>被提出的承诺</span></div>
    <div class="stat high"><b>{run.claims_dropped}</b><span>逐字核对拒绝</span></div>
  </div>

  <h2>漂移清单</h2>
  {f"<table><thead><tr><th></th><th>类型</th><th>承诺</th><th>实际</th></tr></thead><tbody>{rows}</tbody></table>" if found else "<p class=quiet>没有一条承诺被实现推翻。</p>"}

  {f"<h2>被反方读者驳回（不计入结论）</h2><table><thead><tr><th></th><th>原判</th><th>驳回理由</th></tr></thead><tbody>{lost_rows}</tbody></table>" if lost else ""}

  {f"<h2>模型提出但被逐字核对拒绝</h2><p class=quiet>这些引文在原文里找不到，因此一条都没有进入结论。</p><table><thead><tr><th>文件</th><th>模型给的引文</th><th>拒绝原因</th></tr></thead><tbody>{dropped_rows}</tbody></table>" if dropped_rows else ""}

  <footer>
    证据文件：<code>ledger.json</code> ·
    目标 <code>{html.escape(run.target)}</code> ·
    run_id <code>{html.escape(run.run_id or "—")}</code> ·
    {html.escape(run.started_at)}
  </footer>
</div>
</body>
</html>
"""


def _row(index: int, finding: Finding) -> str:
    impl = finding.implementation
    if impl:
        actual = (
            f'<div class=where>{html.escape(impl.file)}:{impl.line}</div>'
            f'<pre class=quote>{html.escape(impl.snippet or impl.value)}</pre>'
        )
    else:
        actual = '<div class=missing>未找到对应实现</div>'
    return f"""<tr>
  <td class=n>{index}</td>
  <td><span class="tag {SEVERITY_EN[finding.severity]}">{SEVERITY_LABEL[finding.severity]}</span>
      <span class=kind>{html.escape(KIND_LABEL[finding.kind])}</span></td>
  <td><div class=where>{html.escape(finding.claim.file)}:{finding.claim.line}</div>
      <pre class=quote>{html.escape(finding.claim.quote)}</pre></td>
  <td>{actual}</td>
</tr>
<tr><td></td><td colspan=3><p class=why>{html.escape(finding.why or finding.machine_reason)}</p></td></tr>"""


def _lost_row(finding: Finding) -> str:
    return (
        f"<tr><td class=n></td>"
        f"<td><span class=kind>{html.escape(KIND_LABEL[finding.kind])}</span>"
        f"<div class=where>{html.escape(finding.claim.file)}:{finding.claim.line}</div></td>"
        f"<td>{html.escape(finding.rebuttal or '（未给理由）')}</td></tr>"
    )
