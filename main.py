#!/usr/bin/env python3
"""
Seedance 2.0 视频生成桌面工具 - Flask 后端
火山引擎 Seedance 2.0 API 调用工具，支持本地运行
"""

import os
import time
import threading
import flask
from flask import request, jsonify, render_template
import requests
from volcengine_auth import Credentials
from volcengine import VolcEngine

app = flask.Flask(__name__, template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# 全局状态
task_results = {}
VOLCANO_API_BASE = "https://visual.volcengineapi.com"
VOLCANO_REGION = "cn-beijing"


def get_access_token(api_key: str, secret_key: str) -> str:
    """获取火山引擎 Access Token"""
    try:
        credentials = Credentials(access_key=api_key, secret_key=secret_key)
        service_info = {
            'region': VOLCANO_REGION,
            'service': 'visual',
            'host': ' volcarker.com',
            'version': '2022-08-01'
        }
        return credentials.get_access_token()
    except Exception as e:
        raise Exception(f"认证失败: {str(e)}")


def submit_video_task(access_token: str, params: dict) -> str:
    """提交视频生成任务"""
    url = f"{VOLCANO_API_BASE}/api/v1/seedance/video/generation"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    response = requests.post(url, json=params, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get('code') != 0:
        raise Exception(data.get('message', '提交失败'))
    return data['data']['task_id']


def query_task_status(access_token: str, task_id: str) -> dict:
    """查询任务状态"""
    url = f"{VOLCANO_API_BASE}/api/v1/seedance/video/generation/{task_id}"
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def poll_task(access_token: str, task_id: str, callback=None):
    """轮询任务状态直到完成"""
    while True:
        try:
            result = query_task_status(access_token, task_id)
            status = result['data']['status']
            task_results[task_id] = result
            if callback:
                callback(result)
            if status in ['SUCCESS', 'FAILED', 'CANCELLED']:
                break
            time.sleep(5)
        except Exception as e:
            task_results[task_id] = {'error': str(e)}
            break


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/get_token', methods=['POST'])
def api_get_token():
    """获取 Access Token"""
    data = request.json
    api_key = data.get('api_key', '')
    secret_key = data.get('secret_key', '')
    if not api_key or not secret_key:
        return jsonify({'success': False, 'error': '请提供 API Key 和 Secret Key'}), 400
    try:
        token = get_access_token(api_key, secret_key)
        return jsonify({'success': True, 'token': token})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/submit_task', methods=['POST'])
def api_submit_task():
    """提交视频生成任务"""
    data = request.json
    access_token = data.get('access_token', '')
    if not access_token:
        return jsonify({'success': False, 'error': '请先获取 Access Token'}), 400

    # 构建参数
    params = {
        'prompt': data.get('prompt', ''),
        'duration': int(data.get('duration', 6)),
        'aspect_ratio': data.get('aspect_ratio', '16:9'),
    }

    # 可选参数
    if data.get('image_url'):
        params['image_url'] = data['image_url']
    if data.get('audio_url'):
        params['audio_url'] = data['audio_url']

    try:
        task_id = submit_video_task(access_token, params)
        # 后台轮询
        thread = threading.Thread(target=poll_task, args=(access_token, task_id))
        thread.daemon = True
        thread.start()
        return jsonify({'success': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/query_task', methods=['GET'])
def api_query_task():
    """查询任务状态"""
    task_id = request.args.get('task_id', '')
    access_token = request.args.get('access_token', '')
    if not task_id:
        return jsonify({'success': False, 'error': '缺少 task_id'}), 400

    if task_id in task_results:
        return jsonify({'success': True, 'data': task_results[task_id]})

    if access_token:
        try:
            result = query_task_status(access_token, task_id)
            return jsonify({'success': True, 'data': result})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': False, 'error': '缺少 access_token'}), 400


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """上传文件到 Seedance"""
    access_token = request.args.get('access_token', '')
    if not access_token:
        return jsonify({'success': False, 'error': '缺少 access_token'}), 400

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '文件名为空'}), 400

    try:
        url = f"{VOLCANO_API_BASE}/api/v1/seedance/upload"
        headers = {'Authorization': f'Bearer {access_token}'}
        files = {'file': (file.filename, file.read(), file.content_type)}
        response = requests.post(url, files=files, headers=headers, timeout=60)
        response.raise_for_status()
        result = response.json()
        return jsonify({'success': True, 'url': result['data']['url']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5173))
    app.run(host='0.0.0.0', port=port, debug=False)
