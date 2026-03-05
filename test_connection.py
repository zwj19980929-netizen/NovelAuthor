import os
from openai import OpenAI
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")
base_url = "https://api.deepseek.com/v1" # 我们测试带 /v1 的地址

print(f"正在测试连接 DeepSeek API...")
print(f"API Key: {api_key[:5]}******")
print(f"Base URL: {base_url}")

client = OpenAI(api_key=api_key, base_url=base_url)

try:
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "user", "content": "你好，测试一下连接。请回复：连接成功。"}
        ],
        stream=False
    )
    print("\n✅ 测试成功！DeepSeek 回复：")
    print(response.choices[0].message.content)

except Exception as e:
    print("\n❌ 连接失败！详细错误信息如下：")
    print(e)
    print("\n排查建议：")
    print("1. 如果你开了 VPN/代理，请尝试关闭它，或者在代码中配置代理。")
    print("2. 检查你的 API Key 是否欠费。")
    print("3. 确保你的防火墙没有拦截 Python.exe。")