import os
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from collections import Counter

# 引入你的云端 AI 分析模块
from cloud_api import ask_smart_assistant_multimodal, extract_keywords_with_llm, classify_with_llm
import base64

app = FastAPI()

# 确保静态资源目录存在
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 全局结构化内存数据库
learning_system_db = {
    "latest_capture": "",
    "learned_keywords": [],
    "total_records_saved": 0,
    "ai_cognitive_feedback": "系统就绪，等待终端设备摄入新知识...",
    "history_records": [],
    # ====== 新增：关键词分类统计 ======
    "category_stats": {
        "医药": 0,
        "运动": 0,
        "日常": 0,
        "学习": 0,
        "科技": 0,
        "其他": 0
    }
}

# ================= 后端路由接口 =================

@app.post("/upload")
async def receive_from_pi(file: UploadFile = File(...), text: str = Form(...)):
    """
    接收树莓派上传的多模态数据，调用百度千帆大模型进行分析并归档
    """
    # 1. 存储图片（安全提取纯文件名）
    filename = os.path.basename(file.filename)
    file_path = f"static/{filename}"
    file_content = await file.read()
    
    with open(file_path, "wb") as buffer:
        buffer.write(file_content)
           
    # 2. 核心大脑分析：直接用多模态大模型做智慧识图（不经过OCR）
    image_b64 = base64.b64encode(file_content).decode('utf-8')
    ai_prompt = (
        "请结合图片内容和用户输入，做一次完整的智能决策分析。"
        "你的分析将显示在系统看板的「AI 决策分析」区域，请：\n"
        "1. 先描述你从图片中看到了什么（物体、文字、场景等）\n"
        "2. 结合用户输入的文本，做出合理推断\n"
        "3. 给出你的决策建议或结论\n"
        "语气专业、简洁，控制在50字以内。"
    )
    ai_analysis_result = ask_smart_assistant_multimodal(
        prompt_text=f"{ai_prompt}\n\n用户输入：{text}",
        image_base64=image_b64,
        system_prompt="你是一个端云协同系统的AI决策分析引擎，负责看图理解并给出专业判断。",
        model="ernie-5.0"
    )
    if not ai_analysis_result:
        ai_analysis_result = "AI 分析服务暂未响应"
    
        # 3. AI提取关键词（用AI分析文本替代OCR文本，作为关键词提取的语料）
    keywords = extract_keywords_with_llm(text, ai_analysis_result[:150])
    if not keywords:
        keywords = [w for w in (text + " " + ai_analysis_result[:150]).split() if len(w) > 1][:10]
    
    # 4. AI智能分类：结合关键词、用户文本、AI分析文本综合判断
    categories = classify_with_llm(text, ai_analysis_result, keywords)
    
    # 5. 分类计数累加
    for cat in categories:
        if cat in learning_system_db["category_stats"]:
            learning_system_db["category_stats"][cat] += 1
    
    # 6. 结构化归档入库（附带关键词和分类信息）
    record = {
        "id": learning_system_db["total_records_saved"] + 1,
        "image": f"/{file_path}",
        "text": text,
        "time": "刚刚",
        "categories": categories,
        "keywords": keywords  # AI提取的关键词列表
    }
    
    # 插入到历史记录最顶端
    learning_system_db["history_records"].insert(0, record)
    learning_system_db["latest_capture"] = record["image"]
    learning_system_db["ai_cognitive_feedback"] = ai_analysis_result or "AI 分析服务暂未响应"
    
    # 将AI提取的关键词存入词云数据（替换原来的简单分词）
    learning_system_db["learned_keywords"].extend(keywords)
    learning_system_db["total_records_saved"] += 1    
    
    return {"status": "ok", "categories": categories}


@app.get("/api/data")
async def get_data():
    """
    数据网关接口：供前端网页拉取最新统计、标签云、AI状态、分类统计和历史队列
    """
        # 标签云数据：直接从 learned_keywords 累计数组中统计，取前15个高频词
    tag_counts = Counter(learning_system_db["learned_keywords"]).most_common(15)
    tags = [{"name": w, "count": c} for w, c in tag_counts]
    
    # 计算各分类占比（用于前端进度条）
    stats = learning_system_db["category_stats"]
    total = sum(stats.values()) or 1  # 避免除零
    
    return {
        "image": learning_system_db["latest_capture"],
        "tags": tags,
        "analysis": learning_system_db["ai_cognitive_feedback"],
        "records": learning_system_db["total_records_saved"],
        "history": learning_system_db["history_records"],
        # ====== 新增：分类统计 ======
        "category_stats": stats,
        "category_percent": {k: round(v / total * 100, 1) for k, v in stats.items()}
    }


# ================= 前端可视化系统面板 =================

@app.get("/", response_class=HTMLResponse)
async def view_system():
    """
    渲染高级大屏看板：图片 + 词云 + 分类统计 + 历史记录
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>端云协同 - 智慧学习系统</title>
        <meta charset="utf-8">
        <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/toastify-js/src/toastify.min.css">
        <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/toastify-js"></script>
        
        <style>
            body { font-family: 'Segoe UI', Tahoma, sans-serif; background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%); margin: 0; padding: 20px; color: #2c3e50; min-height: 100vh; }
            .header { text-align: center; margin-bottom: 25px; }
            .header h1 { color: #2c3e50; margin-bottom: 10px; font-weight: 800; letter-spacing: 1px; font-size: 1.8em; }
            .db-status { color: #fff; font-weight: bold; background: linear-gradient(to right, #00b09b, #96c93d); padding: 8px 25px; border-radius: 20px; display: inline-block; box-shadow: 0 4px 10px rgba(0,176,155,0.3); }
            
                        /* 左栏(图片+AI)加宽 | 中(词云)弹性 | 右(分类统计)固定 */
            .grid-container { display: grid; grid-template-columns: 480px 1fr 300px; gap: 20px; max-width: 1500px; margin: auto; }
            .card { background: white; padding: 20px; border-radius: 14px; box-shadow: 0 6px 16px rgba(0,0,0,0.04); transition: transform 0.3s ease, box-shadow 0.3s ease; }
            .card:hover { transform: translateY(-3px); box-shadow: 0 12px 24px rgba(0,0,0,0.08); }
            .img-panel { text-align: center; }
            .img-panel img { width: 100%; height: 400px; border-radius: 10px; object-fit: contain; background: #ecf0f1; border: 1px dashed #ddd; }
            
            /* 词云居中占据最大空间 */
            .stats-panel { }
            #wordCloud { width: 100%; height: 560px; }
            
            /* AI分析 */
            .ai-panel { border-left: 5px solid #3498db; background: linear-gradient(to right, #fdfefe, #f4f9ff); }
            .ai-text { font-size: 0.95em; line-height: 1.6; color: #2c3e50; font-family: monospace; min-height: 60px; }
            .cursor { display: inline-block; width: 6px; height: 1em; background-color: #3498db; vertical-align: middle; animation: blink 1s step-end infinite; }
            @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
            h2 { font-size: 1.1em; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; color: #34495e; margin-top: 0; }
            h3 { font-size: 0.95em; color: #555; margin: 12px 0 6px 0; }
            
            /* ====== 分类统计样式 ====== */
            .category-card { }
            .cat-item { margin-bottom: 14px; }
            .cat-header { display: flex; justify-content: space-between; font-size: 0.9em; margin-bottom: 4px; }
            .cat-name { font-weight: 600; }
            .cat-badge { background: #eee; padding: 1px 10px; border-radius: 10px; font-size: 0.85em; }
            .cat-bar-bg { height: 20px; background: #f0f0f0; border-radius: 10px; overflow: hidden; position: relative; }
            .cat-bar-fill { height: 100%; border-radius: 10px; transition: width 0.6s ease; min-width: 0; }
            .cat-bar-text { position: absolute; right: 8px; top: 2px; font-size: 0.75em; color: #555; font-weight: bold; }
            .cat-medicine .cat-bar-fill { background: linear-gradient(90deg, #e74c3c, #f1948a); }
            .cat-sport .cat-bar-fill { background: linear-gradient(90deg, #2ecc71, #82e0aa); }
            .cat-daily .cat-bar-fill { background: linear-gradient(90deg, #f39c12, #f7dc6f); }
            .cat-study .cat-bar-fill { background: linear-gradient(90deg, #3498db, #85c1e9); }
            .cat-tech .cat-bar-fill { background: linear-gradient(90deg, #9b59b6, #c39bd3); }
            .cat-other .cat-bar-fill { background: linear-gradient(90deg, #95a5a6, #d5dbdb); }
            .cat-total { text-align: center; margin-top: 15px; padding: 8px; background: #f8f9fa; border-radius: 8px; font-size: 0.9em; color: #666; }
            
            /* 历史按钮 */
            .history-btn { background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9em; font-weight: bold; transition: background 0.2s; }
            .history-btn:hover { background: #2980b9; }
            #historyModal { display: none; position: fixed; top: 8%; left: 10%; width: 80%; height: 80%; background: white; z-index: 1000; border-radius: 15px; padding: 25px; box-shadow: 0 0 30px rgba(0,0,0,0.3); overflow-y: auto; }
            .close-btn { background: #e74c3c; color: white; padding: 6px 15px; border: none; border-radius: 5px; cursor: pointer; float: right; }
            
            @keyframes pulseGlow {
                0% { transform: scale(1); box-shadow: 0 0 0 rgba(52, 152, 219, 0); }
                50% { transform: scale(1.02); box-shadow: 0 0 25px rgba(52, 152, 219, 0.6); }
                100% { transform: scale(1); box-shadow: 0 6px 16px rgba(0,0,0,0.04); }
            }
            .update-anim { animation: pulseGlow 0.6s ease-out; }

            /* 标签样式 */
            .cat-tag { display: inline-block; font-size: 0.7em; padding: 1px 8px; border-radius: 8px; color: #fff; margin-left: 6px; }
            .tag-medicine { background: #e74c3c; }
            .tag-sport { background: #2ecc71; }
            .tag-daily { background: #f39c12; }
            .tag-study { background: #3498db; }
            .tag-tech { background: #9b59b6; }
            .tag-other { background: #95a5a6; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>☁️ 端云协同智能辅助系统 - 学习中心</h1>
            <button class="history-btn" onclick="toggleHistory()">📂 查看历史学习记录</button>
            <span style="margin:0 10px"></span>
            <div class="db-status">🗄️ 已储存记录: <span id="recordCount">0</span> 条</div>
        </div>

        <div id="historyModal">
            <button class="close-btn" onclick="toggleHistory()">关闭窗口</button>
            <h2 style="border-bottom: 1px solid #eee; padding-bottom:10px;">📂 历史数据深度检索仓</h2>
            <div id="historyList"></div>
        </div>

        <div class="grid-container">
            <!-- 左栏：图片 + AI分析 -->
            <div>
                <div class="card img-panel" id="imgCard">
                    <h2>📷 视觉采集</h2>
                    <img id="captureImg" src="" alt="等待上传...">
                </div>
                <div class="card ai-panel" id="aiCard" style="margin-top:20px;">
                    <h2>🤖 AI 决策分析</h2>
                    <div id="aiAnalysisBox">
                        <span class="ai-text" id="aiAnalysis">引擎等待数据...</span>
                        <span class="cursor"></span>
                    </div>
                </div>
            </div>

                        <!-- 中栏：标签云 -->
            <div class="card stats-panel" id="statsCard">
                <h2>🧠 认知词库 · 多模态特征图谱</h2>
                <div id="tagCloud" style="min-height: 500px; display: flex; flex-wrap: wrap; align-content: flex-start; gap: 8px; padding: 10px;"></div>
            </div>

            <!-- 右栏：关键词分类统计 -->
            <div class="card category-card" id="catCard">
                <h2>📊 关键词分类统计</h2>
                <div id="categoryStats">
                    <div class="cat-item cat-medicine">
                        <div class="cat-header"><span class="cat-name">💊 医药</span><span class="cat-badge" id="cat-medicine-count">0</span></div>
                        <div class="cat-bar-bg"><div class="cat-bar-fill" id="cat-medicine-bar" style="width:0%"><span class="cat-bar-text">0%</span></div></div>
                    </div>
                    <div class="cat-item cat-sport">
                        <div class="cat-header"><span class="cat-name">⚽ 运动</span><span class="cat-badge" id="cat-sport-count">0</span></div>
                        <div class="cat-bar-bg"><div class="cat-bar-fill" id="cat-sport-bar" style="width:0%"><span class="cat-bar-text">0%</span></div></div>
                    </div>
                    <div class="cat-item cat-daily">
                        <div class="cat-header"><span class="cat-name">🏠 日常</span><span class="cat-badge" id="cat-daily-count">0</span></div>
                        <div class="cat-bar-bg"><div class="cat-bar-fill" id="cat-daily-bar" style="width:0%"><span class="cat-bar-text">0%</span></div></div>
                    </div>
                    <div class="cat-item cat-study">
                        <div class="cat-header"><span class="cat-name">📚 学习</span><span class="cat-badge" id="cat-study-count">0</span></div>
                        <div class="cat-bar-bg"><div class="cat-bar-fill" id="cat-study-bar" style="width:0%"><span class="cat-bar-text">0%</span></div></div>
                    </div>
                    <div class="cat-item cat-tech">
                        <div class="cat-header"><span class="cat-name">🔧 科技</span><span class="cat-badge" id="cat-tech-count">0</span></div>
                        <div class="cat-bar-bg"><div class="cat-bar-fill" id="cat-tech-bar" style="width:0%"><span class="cat-bar-text">0%</span></div></div>
                    </div>
                    <div class="cat-item cat-other">
                        <div class="cat-header"><span class="cat-name">❓ 其他</span><span class="cat-badge" id="cat-other-count">0</span></div>
                        <div class="cat-bar-bg"><div class="cat-bar-fill" id="cat-other-bar" style="width:0%"><span class="cat-bar-text">0%</span></div></div>
                    </div>
                    <div class="cat-total">累计分类: <span id="cat-total">0</span> 条</div>
                </div>
            </div>
        </div>

                <script>
            let lastRecordCount = 0;

            function toggleHistory() { 
                let m = document.getElementById('historyModal'); 
                m.style.display = (m.style.display === 'block') ? 'none' : 'block'; 
            }

            // 分类名称映射
            const CAT_KEYS = ['medicine', 'sport', 'daily', 'study', 'tech', 'other'];
            const CAT_NAMES = ['医药', '运动', '日常', '学习', '科技', '其他'];

            function updateCategoryStats(stats, percents) {
                let total = 0;
                for (let i = 0; i < CAT_KEYS.length; i++) {
                    let key = CAT_KEYS[i];
                    let name = CAT_NAMES[i];
                    let count = stats[name] || 0;
                    let pct = percents[name] || 0;
                    total += count;
                    
                    let bar = document.getElementById('cat-' + key + '-bar');
                    let countEl = document.getElementById('cat-' + key + '-count');
                    bar.style.width = pct + '%';
                    bar.querySelector('.cat-bar-text').innerText = pct + '%';
                    countEl.innerText = count;
                }
                document.getElementById('cat-total').innerText = total;
            }

            // 纯 CSS 标签云渲染函数
            const TAG_COLORS = ['#e74c3c','#2ecc71','#f39c12','#3498db','#9b59b6','#1abc9c','#e67e22','#34495e','#16a085','#c0392b'];
            function renderTagCloud(tags) {
                let container = document.getElementById('tagCloud');
                if (!tags || tags.length === 0) {
                    container.innerHTML = '<div style="color:#aaa;text-align:center;width:100%;padding:40px 0;">暂无关键词数据</div>';
                    return;
                }
                let maxCount = Math.max(...tags.map(t => t.count), 1);
                let html = '';
                tags.forEach(t => {
                    let ratio = t.count / maxCount;
                    let fontSize = 12 + Math.round(ratio * 24);  // 12px ~ 36px
                    let color = TAG_COLORS[Math.floor(Math.random() * TAG_COLORS.length)];
                    let opacity = 0.6 + ratio * 0.4;
                    html += `<span style="display:inline-block;font-size:${fontSize}px;color:${color};opacity:${opacity};padding:4px 10px;margin:3px;border-radius:4px;background:#f5f6fa;border:1px solid #eee;transition:all 0.2s;cursor:default;" title="出现 ${t.count} 次">${t.name}</span>`;
                });
                container.innerHTML = html;
            }

            async function fetchData() {
                try {
                    let response = await fetch('/api/data');
                    let data = await response.json();
                    
                    // 1. 图片
                    if(data.image) document.getElementById('captureImg').src = data.image;
                    
                    // 2. 记录数
                    document.getElementById('recordCount').innerText = data.records;
                    
                    // 3. AI分析
                    document.getElementById('aiAnalysis').innerText = data.analysis || 'AI 分析服务暂未响应';
                    
                                        // 4. 标签云（纯 CSS，不依赖任何第三方库）
                    renderTagCloud(data.tags || []);

                    // 5. 历史记录
                    let hList = document.getElementById('historyList');
                    hList.innerHTML = data.history.map(h => {
                        let tags = (h.categories || []).map(c => {
                            let cls = c === '医药' ? 'tag-medicine' : c === '运动' ? 'tag-sport' : c === '日常' ? 'tag-daily' : c === '学习' ? 'tag-study' : c === '科技' ? 'tag-tech' : 'tag-other';
                            return '<span class="cat-tag ' + cls + '">' + c + '</span>';
                        }).join('');
                        return `
                            <div style="padding:12px; border-bottom:1px solid #f0f0f0; display:flex; align-items:center; gap:15px;">
                                <img src="${h.image}" style="width:80px; height:55px; object-fit:contain; background:#fafafa; border-radius:5px; border:1px solid #eee;">
                                <div>
                                    <span style="color:#3498db; font-weight:bold;">#${h.id}</span> 
                                    <span style="color:#aaa; font-size:0.8em;">${h.time}</span>
                                    ${tags}
                                    <p style="margin:4px 0 0 0; font-size:0.85em; color:#555;"><b>文本:</b> ${h.text.substring(0, 60)}</p>
                                </div>
                            </div>
                        `;
                    }).join('');
                    
                    // 6. 分类统计（核心新增！）
                    if (data.category_stats) {
                        updateCategoryStats(data.category_stats, data.category_percent);
                    }
                    
                    // 7. 新记录特效
                    if (data.records > lastRecordCount && lastRecordCount !== 0) {
                        Toastify({
                            text: "🔔 接收到 RA8D1 智能分类数据！",
                            duration: 3000,
                            gravity: "top", position: "right",
                            style: { background: "linear-gradient(to right, #00b09b, #96c93d)", borderRadius: "8px", fontWeight: "bold" }
                        }).showToast();
                        document.getElementById('imgCard').classList.add('update-anim');
                        document.getElementById('aiCard').classList.add('update-anim');
                        document.getElementById('catCard').classList.add('update-anim');
                        setTimeout(() => {
                            document.getElementById('imgCard').classList.remove('update-anim');
                            document.getElementById('aiCard').classList.remove('update-anim');
                            document.getElementById('catCard').classList.remove('update-anim');
                        }, 600);
                    }
                    lastRecordCount = data.records;

                } catch (error) { 
                    console.error("数据总线同步异常:", error); 
                }
            }

                        fetchData();
            setInterval(fetchData, 1500);
        </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    # 绑定全网卡，监听 8000 端口
    uvicorn.run(app, host="0.0.0.0", port=8000)