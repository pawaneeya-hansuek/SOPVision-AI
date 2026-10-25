"""Optional Gemini image review shared by standard reports and QR attempts."""
from __future__ import annotations

import os
from pathlib import Path


def review_images(prompt: str, image_paths: list[Path]) -> dict[str, str]:
    if not os.getenv('GEMINI_API_KEY'):
        raise ValueError('ยังไม่ได้ตั้ง GEMINI_API_KEY ในเครื่องเซิร์ฟเวอร์')
    if not image_paths:
        raise ValueError('รายการนี้ยังไม่มีภาพหลักฐานสำหรับให้ AI ตรวจ')
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise ValueError('ติดตั้ง google-genai ก่อนเปิดใช้งาน AI Review') from error

    contents: list = [prompt]
    for image_path in image_paths[:5]:
        image_bytes = image_path.read_bytes()
        if not image_bytes:
            raise ValueError('ไฟล์ภาพหลักฐานว่างเปล่า')
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'))

    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    response = client.models.generate_content(
        model=os.getenv('GEMINI_MODEL', 'gemini-flash-latest'),
        contents=contents,
    )
    return {
        'text': response.text or 'โมเดลไม่ส่งข้อความตอบกลับ',
        'note': 'AI เป็นผู้ช่วยตีความภาพ ไม่ใช่การยืนยันผลตรวจขั้นตอน',
    }
