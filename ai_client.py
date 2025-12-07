#!/usr/bin/env python3

import os
import requests
import json
from pathlib import Path
from typing import Optional, Dict, Any


class AIClient:
    
    def __init__(self, api_key_file: str = "neuroKEY.txt"):
        self.api_key = self._read_api_key(api_key_file)
        self.base_url = "https://api.x.ai/v1"
        self.chat_url = f"{self.base_url}/chat/completions"
    
    def _read_api_key(self, filename: str) -> str:
        try:
            key_path = Path(filename)
            if not key_path.exists():
                raise FileNotFoundError(f"none: {filename}")
            
            api_key = key_path.read_text(encoding="utf-8").strip()
            if not api_key:
                raise ValueError(f"empty: {filename}")
            
            return api_key
        except Exception as e:
            raise RuntimeError(f"fail: {e}")
    
    def chat(self, 
             message: str, 
             model: str = "grok-4", 
             temperature: float = 0.7,
             stream: bool = False) -> Dict[str, Any]:
    
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
            response.raise_for_status()  
            
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = f"fail: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f"\n: {error_detail}"
                except:
                    error_msg += f"\n: {e.response.text}"
            raise RuntimeError(error_msg)
    
    def get_response_text(self, response: Dict[str, Any]) -> str:
        try:
            choices = response.get("choices", [])
            if choices and len(choices) > 0:
                message = choices[0].get("message", {})
                return message.get("content", "")
            return ""
        except Exception as e:
            raise ValueError(f"fail: {e}")


