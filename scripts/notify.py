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
    "leverage": "杠杆代理",
    "wwi": "龙波指数",
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
    if key == "leverage":
        return "{:.4f}".format(value)
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

    if kind == "alert":
        subject = "[龙波预警] {}".format(risk["label"])
        lead = "风险状态刚刚进入高关注区间，请结合各项指标审慎判断。"
    elif kind == "test":
        subject = "[龙波] 邮件配置测试"
        lead = "邮件通道配置成功，之后将按计划发送日报与风险预警。"
    else:
        subject = "[龙波日报] {} · {}".format(now.strftime("%m月%d日"), risk["label"])
        lead = "以下为北京时间 {} 的 BTC 周期监控摘要。".format(now.strftime("%Y-%m-%d %H:%M"))

    text_lines = [
        subject,
        lead,
        "",
        "当前状态：{}（综合风险分 {}）".format(risk["label"], risk_score if risk_score is not None else "--"),
        "未来七日：{}".format(outlook.get("label", "暂无法判断")),
        "",
        "指标                最新值        1日变化      7日变化",
    ]

    rows = []
    for key, label in LABELS.items():
        metric = current.get(key, {})
        value = format_value(key, metric.get("value"))
        day = format_change(metric.get("change1d"))
        week = format_change(metric.get("change7d"))
        text_lines.append("{:<20} {:>12} {:>11} {:>11}".format(label, value, day, week))
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(label), html.escape(value), html.escape(day), html.escape(week)
            )
        )

    text_lines.extend(
        [
            "",
            outlook.get("detail", ""),
            "",
            "数据仅用于周期观察，不构成投资建议。",
        ]
    )

    html_body = """<!doctype html>
<html lang="zh-CN"><body style="margin:0;background:#f4f6f8;color:#172026;font-family:Arial,'Microsoft YaHei',sans-serif">
<div style="max-width:680px;margin:0 auto;padding:28px 16px">
  <div style="background:#101619;color:#f7fafb;padding:24px;border-radius:8px 8px 0 0">
    <div style="font-size:13px;color:#9eb0b8">DRAGON WAVE · BTC CYCLE MONITOR</div>
    <h1 style="font-size:24px;line-height:1.35;margin:10px 0 8px">{subject}</h1>
    <p style="margin:0;color:#c7d1d5">{lead}</p>
  </div>
  <div style="background:#fff;padding:24px;border:1px solid #dce3e7;border-top:0">
    <div style="border-left:4px solid #ea6a4a;padding-left:14px;margin-bottom:22px">
      <div style="font-size:13px;color:#65757d">当前风险状态 · 综合风险分 {score}</div>
      <div style="font-size:20px;font-weight:700;margin-top:4px">{risk}</div>
    </div>
    <div style="font-size:13px;color:#65757d">未来七日判断</div>
    <div style="font-size:17px;font-weight:700;margin:5px 0 5px">{outlook}</div>
    <p style="font-size:14px;line-height:1.6;color:#52636b;margin:0 0 22px">{detail}</p>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
      <thead><tr><th style="text-align:left;padding:10px 8px;border-bottom:1px solid #dce3e7">指标</th><th style="text-align:right;padding:10px 8px;border-bottom:1px solid #dce3e7">最新值</th><th style="text-align:right;padding:10px 8px;border-bottom:1px solid #dce3e7">1日</th><th style="text-align:right;padding:10px 8px;border-bottom:1px solid #dce3e7">7日</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <div style="padding:15px 2px;color:#7b898f;font-size:12px;line-height:1.6">数据仅用于周期观察，不构成投资建议。链上指标为日更，价格与杠杆代理尽量实时更新。</div>
</div>
</body></html>""".format(
        subject=html.escape(subject),
        lead=html.escape(lead),
        score=html.escape(str(risk_score if risk_score is not None else "--")),
        risk=html.escape(risk["label"]),
        outlook=html.escape(outlook.get("label", "暂无法判断")),
        detail=html.escape(outlook.get("detail", "")),
        rows="".join(rows),
    )
    return subject, "\n".join(text_lines), html_body


def send_email(address, app_password, subject, text_body, html_body):
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


def main():
    parser = argparse.ArgumentParser(description="Send Dragon Wave email notifications")
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
    print("Sent {} email to {}".format(kind, address))


if __name__ == "__main__":
    main()

