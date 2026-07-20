import requests
import os

# ================= 配置区 =================
# 建议将 URL 独立出来，方便后期改为云端地址
#SERVER_URL = "http://127.0.0.1:8000/upload"
SERVER_URL = "https://edge-cloud-connect-blind-word-array-in.onrender.com/upload"
TEST_IMAGE = "a2.jpg" 

def run_integration_test():
    print("🚀 开始端云协同集成测试...")
    
    # 1. 检查图片
    if not os.path.exists(TEST_IMAGE):
        print(f"❌ 错误：未找到测试图片 {TEST_IMAGE}，请检查路径。")
        return

    # 2. 模拟树莓派采集到的数据
    # 这里我们将提问文字设为变量，模拟真实学习场景
    user_question = "你看这个是什么？"
    
    print(f"📡 [终端] 正在向云端发送数据: {TEST_IMAGE} | 识别文本: {user_question}")

    try:
        # 使用二进制读取模式
        with open(TEST_IMAGE, "rb") as f:
            # 这里的 "file" 必须与 server.py 中 receive_from_pi 的参数名一致
            files = {"file": (TEST_IMAGE, f, "image/jpeg")}
            data = {"text": user_question}
            
            # 发送请求
            response = requests.post(SERVER_URL, files=files, data=data)
            
            # 处理响应
            if response.status_code == 200:
                print("✅ [终端] 上传成功！云端已完成 AI 深度认知分析。")
                print("👀 [状态] 请查看网页端看板界面获取分析报告。")
            else:
                print(f"❌ [错误] 云端返回代码: {response.status_code}")
                print(f"   [详情]: {response.text}")
                
    except requests.exceptions.ConnectionError:
        print("❌ [错误] 无法连接到服务器，请检查 server.py 是否在运行。")
    except Exception as e:
        print(f"❌ [异常] 测试过程发生故障: {e}")

if __name__ == "__main__":
    run_integration_test()