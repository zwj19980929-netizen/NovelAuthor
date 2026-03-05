# utils/email_sender.py
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr  # 🔥 引入这个标准工具
from config import SMTP_CONFIG


def send_verification_email(to_email: str, code: str):
    """发送 6 位数字验证码"""

    subject = "【TrinityAI】注册验证码"
    content = f"""
    <div style="padding: 20px; background-color: #f3f4f6;">
        <div style="background-color: #ffffff; padding: 24px; border-radius: 12px; max-width: 500px; margin: 0 auto;">
            <h2 style="color: #333;">欢迎加入 TrinityAI</h2>
            <p style="color: #666;">您正在申请注册账号，验证码如下：</p>
            <div style="font-size: 32px; font-weight: bold; color: #000; letter-spacing: 4px; margin: 20px 0;">
                {code}
            </div>
            <p style="color: #999; font-size: 12px;">验证码 10 分钟内有效。如非本人操作，请忽略此邮件。</p>
        </div>
    </div>
    """

    message = MIMEText(content, 'html', 'utf-8')

    # 🔥 核心修改：使用 formataddr 生成标准的 From 头
    # 格式必须是： "昵称 <your_email@qq.com>"
    # 这里的 SMTP_CONFIG["USER"] 必须和你 config.py 里填的账号一模一样
    message['From'] = formataddr(("TrinityAI Security", SMTP_CONFIG["USER"]))

    message['To'] = Header(to_email, 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')

    try:
        if SMTP_CONFIG["USE_SSL"]:
            server = smtplib.SMTP_SSL(SMTP_CONFIG["SERVER"], SMTP_CONFIG["PORT"])
        else:
            server = smtplib.SMTP(SMTP_CONFIG["SERVER"], SMTP_CONFIG["PORT"])

        server.login(SMTP_CONFIG["USER"], SMTP_CONFIG["PASSWORD"])
        server.sendmail(SMTP_CONFIG["USER"], to_email, message.as_string())
        server.quit()
        print(f"✅ 邮件已发送至 {to_email}")
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        # 这里可以选择不 raise e，以免 crash 掉整个服务器，
        # 但如果是开发阶段，raise 可以让你看到错误。
        # 生产环境建议只 log 错误。
        raise e