import argparse
import html
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from model import beijing_now, risk_state


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "metrics.json"
STATE_PATH = ROOT / "data" / "notification-state.json"

LABELS = {
    "price": "BTC 现货价格",
    "nupl": "NUPL",
    "realizedPrice": "已实现价格",
    "mvrv": "MVRV",
    "mvrvZ": "MVRV Z-Score",
    "wwi": "狼波周期指数",
}


def read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def format_value(key, value):
    if value is None:
        return "暂不可用"
    if key in ("price", "realizedPrice"):
        return "${:,.0f}".format(value)
    if key == "nupl":
        return "{:.3f}".format(value)
    if key in ("mvrv", "mvrvZ"):
        return "{:.2f}".format(value)
    if key == "wwi":
        return "{:.3f}".format(value)
    return str(value)


def format_change(value):
    if value is None:
        return "--"
    return "{:+.2f}%".format(value)


def build_email(data, state_info, kind):
    now = beijing_now()
    current = data.get("current", {})
    assessment = data.get("assessment", {})
    risk = state_info
    outlook = assessment.get("outlook7d", {})
    risk_score = assessment.get("riskScore")
    forecast = assessment.get("bottomForecast", {})
    forecast_values = forecast.get("values", {})
    forecast_date = forecast.get("targetDate") or forecast.get("asOf") or "--"

    if kind == "alert":
        subject = "[LFCX EPOCH · 预警] {}".format(risk["label"])
        lead = "风险状态刚刚进入高关注区间，请结合各项指标审慎判断。"
    elif kind == "test":
        subject = "[LFCX EPOCH] 邮件配置测试"
        lead = "邮件通道配置成功，之后将按计划发送日报与风险预警。"
    else:
        subject = "[LFCX EPOCH · 日报] {} · {}".format(now.strftime("%m月%d日"), risk["label"])
        lead = "以下为北京时间 {} 的 BTC 周期监控摘要。".format(now.strftime("%Y-%m-%d %H:%M"))

    text_lines = [
        subject,
        lead,
        "",
        "当前状态：{}（综合风险分 {}）".format(risk["label"], risk_score if risk_score is not None else "--"),
        "未来七日：{}".format(outlook.get("label", "暂无法判断")),
        "预测底部日期：{}（动态模型估计）".format(forecast_date),
        "",
        "指标                最新值       预测底部值      1日变化      7日变化",
    ]

    rows = []
    for index, (key, label) in enumerate(LABELS.items()):
        metric = current.get(key, {})
        value = format_value(key, metric.get("value"))
        forecast_value = (
            format_value(key, forecast_values.get(key))
            if forecast_values.get(key) is not None
            else "--"
        )
        day = format_change(metric.get("change1d"))
        week = format_change(metric.get("change7d"))
        text_lines.append(
            "{:<20} {:>12} {:>14} {:>11} {:>11}".format(
                label,
                value,
                forecast_value,
                day,
                week,
            )
        )
        row_background = "#1d2225" if index % 2 else "#181c1f"
        cell_base = (
            "padding:10px 8px;border:1px solid #465158;"
            "line-height:1.35;font-size:12px"
        )
        day_color = (
            "#ff9b86"
            if metric.get("change1d") is not None
            and metric.get("change1d") < 0
            else "#77c9a5"
            if metric.get("change1d") is not None
            and metric.get("change1d") > 0
            else "#e8edef"
        )
        week_color = (
            "#ff9b86"
            if metric.get("change7d") is not None
            and metric.get("change7d") < 0
            else "#77c9a5"
            if metric.get("change7d") is not None
            and metric.get("change7d") > 0
            else "#e8edef"
        )
        rows.append(
            (
                '<tr bgcolor="{row_background}">'
                '<td class="metric-cell metric-label" width="29%" align="left" '
                'style="{cell_base};background:{row_background};color:#e8edef;word-break:break-word">{label}</td>'
                '<td class="metric-cell" width="18%" align="right" '
                'style="{cell_base};background:{row_background};color:#e8edef;white-space:nowrap">{value}</td>'
                '<td class="metric-cell" width="25%" align="right" bgcolor="#312c20" '
                'style="{cell_base};background:#312c20;color:#f2d889;white-space:nowrap">{forecast}</td>'
                '<td class="metric-cell" width="14%" align="right" '
                'style="{cell_base};background:{row_background};color:{day_color};white-space:nowrap">{day}</td>'
                '<td class="metric-cell" width="14%" align="right" '
                'style="{cell_base};background:{row_background};color:{week_color};white-space:nowrap">{week}</td>'
                "</tr>"
            ).format(
                row_background=row_background,
                cell_base=cell_base,
                label=html.escape(label),
                value=html.escape(value),
                forecast=html.escape(forecast_value),
                day=html.escape(day),
                week=html.escape(week),
                day_color=day_color,
                week_color=week_color,
            )
        )

    text_lines.extend(
        [
            "",
            outlook.get("detail", ""),
            "",
            "预测底部值为动态模型估计，并非价格承诺。",
            "数据仅用于周期观察，不构成投资建议。",
        ]
    )

    header_cell = (
        "padding:10px 8px;border:1px solid #465158;line-height:1.35;"
        "font-size:11px;font-weight:700"
    )
    html_body = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="color-scheme" content="dark" />
  <meta name="supported-color-schemes" content="dark" />
  <style type="text/css">
    @media only screen and (max-width:520px) {{
      .mail-gutter {{ padding:10px 6px !important; }}
      .mail-section {{ padding:18px 12px !important; }}
      .metric-cell {{ padding:8px 3px !important; font-size:10px !important; }}
      .metric-label {{ white-space:normal !important; }}
      .mail-title {{ font-size:20px !important; }}
    }}
  </style>
</head>
<body bgcolor="#0e1113" style="margin:0;padding:0;background:#0e1113;color:#e8edef;font-family:Arial,'Microsoft YaHei',sans-serif">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#0e1113" style="width:100%;background:#0e1113;border-collapse:collapse">
    <tr>
      <td class="mail-gutter" align="center" style="padding:28px 16px">
        <table class="mail-shell" role="presentation" width="680" cellspacing="0" cellpadding="0" border="0" bgcolor="#181c1f" style="width:100%;max-width:680px;background:#181c1f;border:1px solid #343c41;border-collapse:collapse">
          <tr>
            <td bgcolor="#0d1113" style="padding:24px;background:#0d1113;color:#f3f6f7;border-bottom:1px solid #343c41">
              <div style="font-size:12px;line-height:1.4;color:#8fa1aa">LFCX EPOCH · DAILY MONITOR</div>
              <div class="mail-title" style="font-size:23px;line-height:1.35;font-weight:700;margin:9px 0 7px;color:#f3f6f7">{subject}</div>
              <div style="font-size:13px;line-height:1.55;color:#aebbc1">{lead}</div>
            </td>
          </tr>
          <tr>
            <td class="mail-section" bgcolor="#181c1f" style="padding:24px;background:#181c1f;color:#e8edef">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;border-collapse:collapse;margin:0 0 20px">
                <tr>
                  <td width="4" bgcolor="#ff7658" style="width:4px;background:#ff7658;font-size:1px;line-height:1px">&#160;</td>
                  <td style="padding-left:13px">
                    <div style="font-size:12px;line-height:1.4;color:#93a3aa">当前风险状态 · 综合风险分 {score}</div>
                    <div style="font-size:20px;line-height:1.4;font-weight:700;color:#f3f6f7;margin-top:4px">{risk}</div>
                  </td>
                </tr>
              </table>
              <div style="font-size:12px;line-height:1.4;color:#93a3aa">未来七日判断</div>
              <div style="font-size:16px;line-height:1.45;font-weight:700;color:#eef2f3;margin:5px 0">{outlook}</div>
              <div style="font-size:13px;line-height:1.6;color:#aebbc1;margin:0 0 18px">{detail}</div>
              <div style="font-size:11px;line-height:1.45;color:#93a3aa;margin:0 0 8px">底部预测 · 动态估计 {forecast_date}</div>
              <table data-role="metrics" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%;table-layout:fixed;border-collapse:collapse;border:1px solid #465158;font-variant-numeric:tabular-nums">
                <thead>
                  <tr bgcolor="#252b2f">
                    <th width="29%" align="left" style="{header_cell};background:#252b2f;color:#b8c3c8">指标</th>
                    <th width="18%" align="right" style="{header_cell};background:#252b2f;color:#b8c3c8">最新值</th>
                    <th width="25%" align="right" bgcolor="#403720" style="{header_cell};background:#403720;color:#ffe29a">预测底部值</th>
                    <th width="14%" align="right" style="{header_cell};background:#252b2f;color:#b8c3c8">1 日</th>
                    <th width="14%" align="right" style="{header_cell};background:#252b2f;color:#b8c3c8">7 日</th>
                  </tr>
                </thead>
                <tbody>{rows}</tbody>
              </table>
            </td>
          </tr>
          <tr>
            <td bgcolor="#111518" style="padding:14px 18px;background:#111518;color:#84949b;font-size:11px;line-height:1.55;border-top:1px solid #343c41">
              预测底部值为动态模型估计，并非价格承诺。数据仅用于周期观察，不构成投资建议。链上指标为日更，BTC 价格尽量实时更新。
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>""".format(
        subject=html.escape(subject),
        lead=html.escape(lead),
        score=html.escape(str(risk_score if risk_score is not None else "--")),
        risk=html.escape(risk["label"]),
        outlook=html.escape(outlook.get("label", "暂无法判断")),
        detail=html.escape(outlook.get("detail", "")),
        forecast_date=html.escape(str(forecast_date)),
        header_cell=header_cell,
        rows="".join(rows),
    )
    return subject, "\n".join(text_lines), html_body


def send_email(address, app_password, subject, text_body, html_body):
    try:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = address
        message["To"] = address
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as smtp:
            smtp.login(address, app_password)
            smtp.send_message(message)
    except Exception:
        # Errors at this boundary may contain recipient details. Keep public CI logs generic.
        raise RuntimeError("Email delivery failed; check the Gmail Actions secrets and account settings") from None


def main():
    parser = argparse.ArgumentParser(description="Send LFCX Epoch email notifications")
    parser.add_argument("--mode", choices=("auto", "daily", "alert", "test"), default="auto")
    args = parser.parse_args()

    data = read_json(DATA_PATH, {})
    if not data:
        raise RuntimeError("metrics.json is missing; run update_data.py first")

    state = read_json(
        STATE_PATH,
        {"lastDailyDate": None, "lastAlertZone": "neutral", "lastSentAt": None},
    )
    score = data.get("assessment", {}).get("riskScore")
    current_state = risk_state(score)
    current_zone = current_state["key"]
    now = beijing_now()
    critical = current_zone in ("near_top", "near_bottom")
    daily_due = 22 <= now.hour <= 23 and state.get("lastDailyDate") != now.date().isoformat()
    alert_due = critical and state.get("lastAlertZone") != current_zone

    kind = None
    if args.mode == "test":
        kind = "test"
    elif args.mode == "daily":
        kind = "daily"
    elif args.mode == "alert":
        kind = "alert" if critical else None
    elif alert_due:
        kind = "alert"
    elif daily_due:
        kind = "daily"

    if not critical and state.get("lastAlertZone") != "neutral":
        state["lastAlertZone"] = "neutral"
        write_json(STATE_PATH, state)

    if kind is None:
        print("No email is due")
        return

    address = os.environ.get("GMAIL_ADDRESS", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not address or not app_password:
        print("Email is due, but Gmail secrets are not configured")
        return

    subject, text_body, html_body = build_email(data, current_state, kind)
    send_email(address, app_password, subject, text_body, html_body)
    if kind == "daily":
        state["lastDailyDate"] = now.date().isoformat()
    if kind == "alert":
        state["lastAlertZone"] = current_zone
    state["lastSentAt"] = now.isoformat()
    write_json(STATE_PATH, state)
    print("Sent {} email".format(kind))


if __name__ == "__main__":
    main()
