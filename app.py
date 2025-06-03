from flask import Flask, request, jsonify, session
import requests
import uuid
from datetime import datetime, timedelta
import json
import logging
import os

app = Flask(__name__)

# 配置会话密钥和设置
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)  # 会话持续24小时

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Google API Key - 优先使用环境变量
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', "AIzaSyCy_1x6sB__B-qGTMCJszIDeJwpDT_hvnc")

# 存储对话历史的内存字典（生产环境建议使用Redis或数据库）
conversation_history = {}

# 清理过期对话的间隔（秒）
CLEANUP_INTERVAL = 3600  # 1小时
last_cleanup = datetime.now()

def cleanup_expired_conversations():
    """清理过期的对话历史"""
    global conversation_history, last_cleanup
    current_time = datetime.now()
    
    if (current_time - last_cleanup).seconds > CLEANUP_INTERVAL:
        expired_sessions = []
        for session_id, data in conversation_history.items():
            if (current_time - data['last_activity']).total_seconds() > 86400:  # 24小时
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del conversation_history[session_id]
        
        last_cleanup = current_time
        logger.info(f"Cleaned up {len(expired_sessions)} expired conversations")

def get_or_create_session_id():
    """获取或创建会话ID"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        session.permanent = True
    return session['session_id']

def get_conversation_history(session_id):
    """获取对话历史"""
    if session_id not in conversation_history:
        conversation_history[session_id] = {
            'messages': [],
            'created_at': datetime.now(),
            'last_activity': datetime.now()
        }
    return conversation_history[session_id]

def add_to_conversation_history(session_id, question, answer):
    """添加对话到历史记录"""
    history = get_conversation_history(session_id)
    history['messages'].append({
        'question': question,
        'answer': answer,
        'timestamp': datetime.now().isoformat()
    })
    history['last_activity'] = datetime.now()
    
    # 限制历史记录长度，保留最近20轮对话
    if len(history['messages']) > 20:
        history['messages'] = history['messages'][-20:]

def build_context_for_api(session_id, current_question):
    """构建包含上下文的API请求内容，确保角色正确。"""
    history_data = get_conversation_history(session_id)
    new_contents = []
    
    system_instruction_text = "你是一个智能助手，请根据对话历史和当前问题提供准确、有用的回答。保持对话的连贯性和上下文理解。"

    # Get the last 5 turns (a turn consists of a user question and a model answer)
    # Each message in history_data['messages'] is one turn.
    recent_messages_from_history = history_data['messages'][-5:]

    if not recent_messages_from_history: # No prior messages in history, this is the first effective turn
        new_contents.append({
            "role": "user",
            "parts": [{"text": system_instruction_text + "\n\n当前问题: " + current_question}]
        })
    else:
        # Add historical messages
        for i, msg_turn in enumerate(recent_messages_from_history):
            user_text_from_history = msg_turn['question']
            # Prepend system instruction only to the very first user message of the whole context
            if i == 0:
                contextual_user_text = system_instruction_text + "\n\n用户历史提问: " + user_text_from_history
            else:
                contextual_user_text = "用户历史提问: " + user_text_from_history
            
            new_contents.append({
                "role": "user",
                "parts": [{"text": contextual_user_text}]
            })
            new_contents.append({
                "role": "model",
                "parts": [{"text": f"{msg_turn['answer']}"}] # Assuming 'answer' is just the text part
            })
        
        # Add the current question from the user
        new_contents.append({
            "role": "user",
            "parts": [{"text": f"当前问题: {current_question}"}]
        })
            
    return new_contents

@app.route('/')
def index():
    """Serves the HTML file from the static directory."""
    return app.send_static_file('index.html')

@app.route('/ask', methods=['POST'])
def ask_google_api():
    """处理问题并调用Google API，支持多轮对话"""
    try:
        cleanup_expired_conversations()
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求数据格式错误"}), 400
        
        question = data.get('question', '').strip()
        if not question:
            return jsonify({"error": "请提供有效的问题"}), 400
        
        session_id = get_or_create_session_id()
        logger.info(f"Processing question for session {session_id}: {question[:100]}...")
        
        api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
        params = {"key": GOOGLE_API_KEY}
        
        # 构建包含对话历史的请求体
        # Option 1: `system_instruction` at top level (often preferred)
        # system_prompt_for_payload = {
        #     "parts": [{"text": "你是一个智能助手，请根据对话历史和当前问题提供准确、有用的回答。保持对话的连贯性和上下文理解。"}]
        # }
        # if build_context_for_api is modified to NOT include system prompt:
        # payload = {
        #     "system_instruction": system_prompt_for_payload,
        #     "contents": build_context_for_api(session_id, question), # build_context_for_api wouldn't add it
        #     # ... rest of payload
        # }

        # Option 2: (As implemented in build_context_for_api above) system prompt is integrated into first user message.
        payload = {
            "contents": build_context_for_api(session_id, question),
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 2048,
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
            ]
        }
        
        logger.debug(f"Sending payload to Google API: {json.dumps(payload, indent=2, ensure_ascii=False)}")

        response = requests.post(
            api_url, 
            params=params, 
            json=payload,
            timeout=30,
            headers={'Content-Type': 'application/json'}
        )
        
        response.raise_for_status()
        api_result = response.json()
        
        answer = extract_answer_from_response(api_result)
        
        if not answer:
            logger.warning(f"Empty answer from API for session {session_id}. API Result: {api_result}")
            answer = "抱歉，我无法为您的问题提供答案。请尝试重新描述您的问题。"
        
        add_to_conversation_history(session_id, question, answer)
        
        history = get_conversation_history(session_id)
        conversation_count = len(history['messages'])
        
        logger.info(f"Successfully processed question for session {session_id}, conversation #{conversation_count}")
        
        return jsonify({
            "answer": answer,
            "session_id": session_id,
            "conversation_count": conversation_count,
            "timestamp": datetime.now().isoformat()
        })
        
    except requests.exceptions.Timeout:
        logger.error("API request timeout")
        return jsonify({"error": "请求超时，请稍后重试"}), 504
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        error_msg = "API调用失败"
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Google API Response Status Code: {e.response.status_code}")
            # Log the full text content of the error response from Google
            logger.error(f"Google API Response Text: {e.response.text}")
            try:
                error_detail = e.response.json()
                # Try to parse Google's common error structure
                if 'error' in error_detail and isinstance(error_detail['error'], dict):
                    message = error_detail['error'].get('message', 'Unknown error from Google API')
                    details = error_detail['error'].get('details', '')
                    error_msg = f"API错误: {message}"
                    if details:
                        error_msg += f" 详情: {json.dumps(details)}" # stringify details if they exist
                elif 'message' in error_detail: # Some error responses might have a simpler structure
                     error_msg = f"API错误: {error_detail.get('message', e.response.text[:200])}"
                else:
                    error_msg = f"API错误: HTTP {e.response.status_code}. 响应片段: {e.response.text[:200]}"
            except json.JSONDecodeError:
                error_msg = f"API错误: HTTP {e.response.status_code}. 响应非JSON格式: {e.response.text[:200]}"
        return jsonify({"error": error_msg}), 500
        
    except json.JSONDecodeError as e: # Error decoding Google's response if it's not JSON for some reason
        logger.error(f"JSON decode error from API response: {e}")
        return jsonify({"error": "API响应格式错误"}), 500
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True) # Log full traceback for unexpected errors
        return jsonify({"error": "服务器内部错误，请稍后重试"}), 500

def extract_answer_from_response(api_result):
    """从API响应中提取答案，并检查安全相关的阻塞"""
    try:
        # Check for prompt feedback (indicates if the prompt itself was blocked)
        if 'promptFeedback' in api_result:
            prompt_feedback = api_result['promptFeedback']
            if 'blockReason' in prompt_feedback:
                reason = prompt_feedback['blockReason']
                logger.error(f"Prompt was blocked by Google API. Reason: {reason}. Details: {prompt_feedback.get('safetyRatings')}")
                return f"抱歉，您的问题因安全设置被API阻止。原因: {reason}"

        # Check candidates for answers or safety blocks
        if 'candidates' in api_result and len(api_result['candidates']) > 0:
            candidate = api_result['candidates'][0]
            if 'content' in candidate and 'parts' in candidate['content'] and len(candidate['content']['parts']) > 0 and 'text' in candidate['content']['parts'][0]:
                return candidate['content']['parts'][0]['text'].strip()
            
            # Check if the generation was stopped due to safety
            if 'finishReason' in candidate:
                finish_reason = candidate['finishReason']
                if finish_reason == 'SAFETY':
                    safety_ratings_info = ""
                    if 'safetyRatings' in candidate:
                        safety_ratings_info = str(candidate['safetyRatings'])
                    logger.warning(f"API response generation stopped due to SAFETY. Ratings: {safety_ratings_info}")
                    return f"抱歉，回答因安全原因 ({finish_reason}) 被终止。详情: {safety_ratings_info}"
                elif finish_reason != 'STOP': # Other finish reasons like MAX_TOKENS, RECITATION etc.
                    logger.warning(f"API response generation finished due to: {finish_reason}")
                    return f"抱歉，回答因 ({finish_reason}) 而未能完成。"
        
        logger.warning(f"Unexpected API response structure or empty answer: {json.dumps(api_result, ensure_ascii=False)}")
        return None
            
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Error extracting answer from API response: {e}, result was: {json.dumps(api_result, ensure_ascii=False)}")
        return None

@app.route('/history', methods=['GET'])
def get_conversation_history_endpoint():
    """获取当前会话的对话历史"""
    try:
        session_id = session.get('session_id')
        if not session_id or session_id not in conversation_history:
            return jsonify({"history": [], "message": "新会话或历史为空"})
        
        history_data = get_conversation_history(session_id)
        return jsonify({
            "history": history_data['messages'],
            "session_id": session_id,
            "created_at": history_data['created_at'].isoformat(),
            "total_messages": len(history_data['messages'])
        })
        
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}", exc_info=True)
        return jsonify({"error": "获取对话历史失败"}), 500

@app.route('/clear', methods=['POST'])
def clear_conversation():
    """清空当前会话的对话历史"""
    try:
        session_id = session.get('session_id')
        if session_id and session_id in conversation_history:
            del conversation_history[session_id]
            logger.info(f"Cleared conversation history for session_id: {session_id}")
        
        session.pop('session_id', None)
        new_session_id = get_or_create_session_id() # Ensure a new session is started
        
        return jsonify({
            "message": "对话历史已清空",
            "new_session_id": new_session_id
        })
        
    except Exception as e:
        logger.error(f"Error clearing conversation: {e}", exc_info=True)
        return jsonify({"error": "清空对话历史失败"}), 500

@app.route('/status', methods=['GET'])
def get_status():
    """获取服务状态"""
    api_key_is_placeholder = GOOGLE_API_KEY == "AIzaSyCy_1x6sB__B-qGTMCJszIDeJwpDT_hvnc" or \
                             GOOGLE_API_KEY == "your-api-key-here" or \
                             not GOOGLE_API_KEY
    return jsonify({
        "status": "running",
        "active_conversations": len(conversation_history),
        "server_time": datetime.now().isoformat(),
        "api_configured": not api_key_is_placeholder,
        "log_level": logging.getLevelName(logger.getEffectiveLevel())
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "接口不存在"}), 404

@app.errorhandler(500)
def internal_error(error): # Flask's default error handler might provide better info if debug=True
    logger.error(f"Unhandled Internal Server Error: {error}", exc_info=True)
    return jsonify({"error": "服务器遇到未处理的内部错误"}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application...")
    
    # 检查API密钥配置
    api_key_is_placeholder = GOOGLE_API_KEY == "AIzaSyCy_1x6sB__B-qGTMCJszIDeJwpDT_hvnc" or \
                             GOOGLE_API_KEY == "your-api-key-here" or \
                             not GOOGLE_API_KEY
    if api_key_is_placeholder:
        logger.warning("IMPORTANT: Google API Key is a placeholder or not set. The application will not be able to connect to Google API.")
        logger.warning("Please set the GOOGLE_API_KEY environment variable or update the key in app.py")
    else:
        logger.info("Google API Key appears to be configured.")
    
    # 环境配置
    debug_mode = os.getenv('FLASK_ENV') != 'production'
    port = int(os.getenv('PORT', 5000))
    
    logger.info(f"Log level set to: {logging.getLevelName(logger.getEffectiveLevel())}")
    logger.info(f"Debug mode: {debug_mode}")
    logger.info(f"Port: {port}")
    
    if logger.getEffectiveLevel() <= logging.DEBUG:
        logger.info("Debug logging is enabled.")

    app.run(
        debug=debug_mode,
        host='0.0.0.0',
        port=port,
        threaded=True
    )
