#!/usr/bin/env python3
"""
Seedance 2.0 - HermeQuant 积分版
火山引擎 Seedance 2.0 AI 视频生成（积分计费）
"""

import os
import json
import time
import threading
import requests
import flask
from flask import request, jsonify, render_template

app = flask.Flask(__name__, template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# ============== 火山引擎 ARK API 配置 ==============
ARK_API_KEY = "5c33b660-38bd-4f9b-b719-3c0f1ff757e8"
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
ARK_MODEL = "doubao-seedance-2-0-260128"
ARK_HEADERS = {
    "Authorization": f"Bearer {ARK_API_KEY}",
    "Content-Type": "application/json",
}

# ============== 任务状态 ==============
task_results = {}
task_cost_map = {}   # task_id -> cost_points

# ============== 导入积分系统 ==============
import credits_manager
credits_manager.init()


def hq_headers():
    return {"Authorization": f"Bearer {ARK_API_KEY}", "Content-Type": "application/json"}


def submit_video_task(params: dict) -> tuple[str, str]:
    """
    提交视频生成任务到火山引擎 ARK API
    返回 (task_id, error_msg)
    """
    payload = {
        "model": ARK_MODEL,
        "content": [
            {"type": "text", "text": params["prompt"]}
        ],
        "ratio": params.get("aspect_ratio", "16:9"),
        "duration": params.get("duration", 6),
        "watermark": False,
    }

    # 参考图片
    if params.get("image_url"):
        payload["content"].append({
            "type": "image_url",
            "image_url": {"url": params["image_url"]},
            "role": "reference_image"
        })

    # 参考音频
    if params.get("audio_url"):
        payload["content"].append({
            "type": "audio_url",
            "audio_url": {"url": params["audio_url"]},
            "role": "reference_audio"
        })

    try:
        resp = requests.post(
            f"{ARK_BASE_URL}/contents/generations/tasks",
            headers=hq_headers(),
            json=payload,
            timeout=30
        )
        data = resp.json()
        if resp.status_code != 200 and resp.status_code != 201:
            return None, f"API错误 {resp.status_code}: {data}"

        task_id = data.get("id") or data.get("data", {}).get("id")
        if not task_id:
            return None, f"未获取到task_id: {data}"
        return task_id, None
    except Exception as e:
        return None, str(e)


def query_task_status(task_id: str) -> tuple[dict, str]:
    """查询任务状态"""
    try:
        resp = requests.get(
            f"{ARK_BASE_URL}/contents/generations/tasks/{task_id}",
            headers=hq_headers(),
            timeout=30
        )
        if resp.status_code == 404:
            return None, "任务不存在"
        resp.raise_for_status()
        return resp.json(), None
    except Exception as e:
        return None, str(e)


def poll_task(task_id: str, cost_points: int):
    """后台轮询任务，完成后处理积分"""
    max_wait = 900  # 15分钟超时
    start = time.time()

    while time.time() - start < max_wait:
        try:
            result, err = query_task_status(task_id)
            if err:
                _handle_failure(task_id, err, cost_points)
                return

            status = result.get("status", "").upper()
            task_results[task_id] = result

            if status == "SUCCEEDED":
                _handle_success(task_id, result, cost_points)
                return
            elif status == "FAILED":
                _handle_failure(task_id, result.get("error", {}).get("message", "任务失败"), cost_points)
                return
            elif status == "CANCELLED":
                _handle_failure(task_id, "任务已取消", cost_points)
                return

            time.sleep(10)
        except Exception as e:
            task_results[task_id] = {"error": str(e)}
            _handle_failure(task_id, str(e), cost_points)
            return

    # 超时
    _handle_failure(task_id, "任务超时（超过15分钟）", cost_points)


def _handle_success(task_id: str, result: dict, cost_points: int):
    task_results[task_id] = {
        "status": "SUCCESS",
        "data": result,
        "cost_points": cost_points,
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _handle_failure(task_id: str, reason: str, cost_points: int):
    task_results[task_id] = {
        "status": "FAILED",
        "error": reason,
        "cost_points": cost_points,
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    credits_manager.refund_balance(cost_points, task_id, reason)


# ============== Flask 路由 ==============

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/balance')
def api_balance():
    """查询积分余额"""
    uid = "default"
    balance = credits_manager.get_balance(uid)
    trans = credits_manager.get_transactions(uid, limit=10)
    return jsonify({
        "success": True,
        "balance": balance,
        "yuan": balance / 10,
        "recent_transactions": trans,
        "rate_table": credits_manager.RATE_TABLE,
    })


@app.route('/api/bonus', methods=['POST'])
def api_bonus():
    """领取新用户赠送"""
    ok, msg = credits_manager.apply_bonus()
    if ok:
        return jsonify({"success": True, "message": msg, "balance": credits_manager.get_balance()})
    return jsonify({"success": False, "message": msg})


@app.route('/api/redeem', methods=['POST'])
def api_redeem():
    """兑换充值码"""
    data = request.json
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"success": False, "error": "请输入充值码"}), 400
    ok, msg = credits_manager.redeem_code(code)
    if ok:
        return jsonify({"success": True, "message": msg, "balance": credits_manager.get_balance()})
    return jsonify({"success": False, "error": msg}), 400


@app.route('/api/transactions')
def api_transactions():
    """交易流水"""
    trans = credits_manager.get_transactions(limit=100)
    return jsonify({"success": True, "transactions": trans})


@app.route('/api/submit', methods=['POST'])
def api_submit():
    """
    提交视频生成任务
    1. 计算积分
    2. 预扣积分
    3. 提交到火山引擎
    4. 后台轮询
    """
    data = request.json
    video_type = data.get("video_type", "text")
    duration = int(data.get("duration", 6))
    has_audio = bool(data.get("audio_url"))

    # 费率计算
    rate_key = credits_manager.get_rate_key(video_type, duration)
    cost = credits_manager.RATE_TABLE[rate_key]["cost"]
    if has_audio:
        cost += credits_manager.RATE_TABLE["audio"]["cost"]

    # 积分预扣
    task_id = f"TASK-{int(time.time()*1000)}"
    ok, msg = credits_manager.deduct_balance(cost, task_id, f"{credits_manager.RATE_TABLE[rate_key]['name']}")
    if not ok:
        return jsonify({"success": False, "error": msg}), 400

    task_cost_map[task_id] = cost

    # 构建火山引擎参数
    params = {
        "prompt": data.get("prompt", ""),
        "aspect_ratio": data.get("aspect_ratio", "16:9"),
        "duration": duration,
        "image_url": data.get("image_url"),
        "audio_url": data.get("audio_url"),
    }

    # 提交到火山引擎
    ark_task_id, err = submit_video_task(params)
    if err:
        credits_manager.refund_balance(cost, task_id, f"火山引擎提交失败: {err}")
        return jsonify({"success": False, "error": f"提交失败: {err}"}), 500

    # 映射本地task_id -> 火山task_id
    task_results[task_id] = {
        "status": "PENDING",
        "ark_task_id": ark_task_id,
        "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 后台轮询
    thread = threading.Thread(target=poll_task, args=(ark_task_id, cost))
    thread.daemon = True
    thread.start()

    return jsonify({
        "success": True,
        "task_id": task_id,
        "ark_task_id": ark_task_id,
        "cost": cost,
        "yuan": cost / 10,
        "message": f"任务已提交，消耗 {cost}积分（{cost/10}元）",
    })


@app.route('/api/query', methods=['GET'])
def api_query():
    """查询任务状态"""
    task_id = request.args.get("task_id")
    if not task_id:
        return jsonify({"success": False, "error": "缺少task_id"}), 400

    if task_id not in task_results:
        return jsonify({"success": False, "error": "任务不存在"}), 404

    return jsonify({"success": True, "data": task_results[task_id]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5173))
    print(f"Seedance 2.0 HermeQuant 积分版启动，端口 {port}")
    print(f"积分存储路径: {credits_manager.DATA_DIR}")
    app.run(host="0.0.0.0", port=port, debug=False)
