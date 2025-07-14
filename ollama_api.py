import requests
import re

url = "http://localhost:11434/api/generate"


# 删除 <think> 标签及其内容，并删除空白行
def clean_response(response):
    # 删除 <think> 标签及其内容
    cleaned_response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
    # 删除空白行
    cleaned_response = "\n".join([line for line in cleaned_response.splitlines() if line.strip()])
    return cleaned_response

def chat(prompt):
    payload = {
        "model": "qwen2.5:3b",
        "prompt": '/nothink\n'+prompt,
        "stream": False
    }
    # 发送对话请求
    try:
        # print('prompt', payload['prompt'])
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            result = response.json()
            result=clean_response(result["response"])
            # print('result',result)
            return result
        else:
            print("请求失败:", response.status_code)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    text="Never believe anything you hear at a woman's tit"
    prompt = (
        f"将下面的这句翻译为中文, 保持原文的语义、语气和风格,直接给出最优的翻译结果,不要在翻译结果后面添加任何注释内容,除了翻译结果不要任何多余的内容,包括解释、注释、说明等,"
        f"不要添加任何注释内容,翻译结果保持一行,不要添加换行符,如果无法翻译则保留原文\n {text}")
    chat(prompt)
