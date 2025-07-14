from openai import OpenAI
import traceback,re

# 初始化 OpenAI 客户端，指定 vLLM 的 API 端点
client = OpenAI(
    base_url="http://192.168.1.112:8000/v1",
    api_key="EMPTY"  # vLLM 不需要 API 密钥，设置为任意值
)

# 删除 <think> 标签及其内容，并删除空白行
def clean_response(response):
    # 删除 <think> 标签及其内容
    cleaned_response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
    # 删除空白行
    cleaned_response = "\n".join([line for line in cleaned_response.splitlines() if line.strip()])
    return cleaned_response


def chat(prompt):
    # 发送对话请求
    try:
        response = client.chat.completions.create(
            model="models/Qwen2.5-72B-Instruct-AWQ",  # 模型路径或 ID
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": '/nothink\n'+prompt}
            ],
            max_tokens=2256,  # 设置最大生成令牌数
            temperature=0.7
        )
        # 打印模型的输出
        return clean_response(response.choices[0].message.content)
    except Exception as e:
        print(f"Error: {e}")
        print(traceback.print_exc())



if __name__ == "__main__":
    # 测试聊天功能
    prompt =   ("将下面的文本由 英文翻译为中文, 保持原文的语义、语气和风格,直接给出最优的翻译结果,不要在翻译结果后面添加任何注释内容,除了翻译结果不要任何多余的内容,包括解释、注释、说明等,不要添加任何注释内容\n Never believe anything you hear at a woman's tit")

    response = chat(prompt)
    print("Response:", response)