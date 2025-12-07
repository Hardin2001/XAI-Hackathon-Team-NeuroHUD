#!/usr/bin/env python3
"""
AI客户端类 - 封装XAI聊天接口调用
在初始化时读取API密钥
"""

import os
import requests
import json
from pathlib import Path
from typing import Optional, Dict, Any


class AIClient:
    """AI客户端类，用于调用XAI聊天接口"""
    
    def __init__(self, api_key_file: str = "neuroKEY.txt"):
        """
        初始化AI客户端
        
        Args:
            api_key_file: API密钥文件路径，默认为"neuroKEY.txt"
        """
        self.api_key = self._read_api_key(api_key_file)
        self.base_url = "https://api.x.ai/v1"
        self.chat_url = f"{self.base_url}/chat/completions"
    
    def _read_api_key(self, filename: str) -> str:
        """
        从文件读取API密钥
        
        Args:
            filename: API密钥文件路径
            
        Returns:
            API密钥字符串
            
        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件为空
        """
        try:
            key_path = Path(filename)
            if not key_path.exists():
                raise FileNotFoundError(f"API密钥文件不存在: {filename}")
            
            api_key = key_path.read_text(encoding="utf-8").strip()
            if not api_key:
                raise ValueError(f"API密钥文件为空: {filename}")
            
            return api_key
        except Exception as e:
            raise RuntimeError(f"读取API密钥失败: {e}")
    
    def chat(self, 
             message: str, 
             model: str = "grok-4", 
             temperature: float = 0.7,
             stream: bool = False) -> Dict[str, Any]:
        """
        发送聊天消息到XAI API
        
        Args:
            message: 用户消息内容
            model: 使用的模型，默认为"grok-4"
            temperature: 温度参数，控制回复的随机性，默认0.7
            stream: 是否使用流式响应，默认False
            
        Returns:
            API响应的JSON字典
            
        Raises:
            requests.exceptions.RequestException: 请求失败
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": message
                }
            ],
            "model": model,
            "stream": stream,
            "temperature": temperature
        }
        
        try:
            response = requests.post(
                self.chat_url, 
                headers=headers, 
                data=json.dumps(payload),
                timeout=30
            )
            response.raise_for_status()  # 如果状态码不是200会抛异常
            
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = f"API请求失败: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f"\n详情: {error_detail}"
                except:
                    error_msg += f"\n响应内容: {e.response.text}"
            raise RuntimeError(error_msg)
    
    def get_response_text(self, response: Dict[str, Any]) -> str:
        """
        从API响应中提取回复文本
        
        Args:
            response: API响应的JSON字典
            
        Returns:
            AI回复的文本内容
        """
        try:
            choices = response.get("choices", [])
            if choices and len(choices) > 0:
                message = choices[0].get("message", {})
                return message.get("content", "")
            return ""
        except Exception as e:
            raise ValueError(f"解析响应失败: {e}")

