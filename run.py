import streamlit as st
import os
import re
import time
import edge_tts
import asyncio
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip
import numpy as np
import markdown
from bs4 import BeautifulSoup
import base64

# 设置页面标题和布局
st.set_page_config(page_title="自动演讲视频生成器", layout="wide")

# 创建临时目录
temp_dir = Path(tempfile.mkdtemp())

# 获取Edge TTS可用音色
async def get_voices():
    voices = await edge_tts.list_voices()
    return voices

# 缓存音色列表
@st.cache_data
def get_voice_list():
    voices = asyncio.run(get_voices())
    return voices

# 解析Markdown文本
def parse_markdown(md_text):
    # 按页分割
    pages = md_text.split('---')
    
    # 解析结果
    result = []
    
    for page in pages:
        if not page.strip():
            continue
            
        # 转换为HTML
        html = markdown.markdown(page)
        soup = BeautifulSoup(html, 'html.parser')
        
        # 提取页面元素
        page_elements = []
        current_element = None
        
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'ul', 'ol']):
            if tag.name.startswith('h'):
                # 如果是标题，创建新元素
                if current_element:
                    page_elements.append(current_element)
                
                current_element = {
                    'type': tag.name,
                    'content': tag.text,
                    'children': []
                }
            else:
                # 如果是内容，添加到当前标题下
                if current_element:
                    current_element['children'].append({
                        'type': tag.name,
                        'content': tag.text
                    })
                else:
                    # 如果没有标题，创建默认标题
                    current_element = {
                        'type': 'h1',
                        'content': '',
                        'children': [{
                            'type': tag.name,
                            'content': tag.text
                        }]
                    }
        
        # 添加最后一个元素
        if current_element:
            page_elements.append(current_element)
            
        result.append(page_elements)
    
    return result

# 生成语音
async def generate_speech(text, voice, output_file):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
    
    # 获取时间信息
    submaker = edge_tts.SubMaker()
    with open(output_file, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.create_sub((chunk["offset"], chunk["duration"]), chunk["text"])
    
    return submaker.subs

# 创建幻灯片图像
def create_slide_image(elements, width=1920, height=1080, bg_color='white'):
    img = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # 加载字体
    try:
        title_font = ImageFont.truetype("msyh.ttc", 60)
        subtitle_font = ImageFont.truetype("msyh.ttc", 48)
        content_font = ImageFont.truetype("msyh.ttc", 36)
    except:
        # 使用默认字体
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        content_font = ImageFont.load_default()
    
    return img, draw, title_font, subtitle_font, content_font

# 创建动画视频
def create_video(parsed_content, voice, bg_color='white'):
    clips = []
    
    for i, page in enumerate(parsed_content):
        # 创建页面图像
        img, draw, title_font, subtitle_font, content_font = create_slide_image(page, bg_color=bg_color)
        
        # 生成页面文本
        page_text = ""
        for element in page:
            page_text += element['content'] + "\n"
            for child in element['children']:
                page_text += child['content'] + "\n"
        
        # 生成语音
        audio_file = temp_dir / f"audio_{i}.mp3"
        subs = asyncio.run(generate_speech(page_text, voice, audio_file))
        
        # 创建动画
        audio_clip = AudioFileClip(str(audio_file))
        duration = audio_clip.duration
        
        # 创建基础图像
        base_img_file = temp_dir / f"base_{i}.png"
        img.save(base_img_file)
        
        # 创建动画元素
        element_clips = []
        current_time = 0
        
        for j, element in enumerate(page):
            # 计算位置
            y_pos = 100 + j * 150
            
            # 创建元素图像
            element_img = img.copy()
            element_draw = ImageDraw.Draw(element_img)
            
            # 绘制标题
            font = title_font if element['type'] == 'h1' else subtitle_font
            element_draw.text((960, y_pos), element['content'], font=font, fill='black', anchor='mt')
            
            # 绘制内容
            content_y = y_pos + 80
            for child in element['children']:
                element_draw.text((100, content_y), child['content'], font=content_font, fill='black')
                content_y += 50
            
            # 保存元素图像
            element_img_file = temp_dir / f"element_{i}_{j}.png"
            element_img.save(element_img_file)
            
            # 创建元素剪辑
            element_duration = 2.0  # 假设每个元素显示2秒
            if j < len(page) - 1:
                element_clip = ImageClip(str(element_img_file)).set_start(current_time).set_duration(element_duration)
            else:
                # 最后一个元素持续到音频结束
                element_clip = ImageClip(str(element_img_file)).set_start(current_time).set_duration(duration - current_time)
            
            element_clips.append(element_clip)
            current_time += element_duration
        
        # 合成页面视频
        page_clip = CompositeVideoClip(element_clips, size=(1920, 1080))
        page_clip = page_clip.set_audio(audio_clip)
        
        clips.append(page_clip)
    
    # 合并所有页面
    final_clip = concatenate_videoclips(clips)
    
    # 保存视频
    output_file = temp_dir / "output.mp4"
    final_clip.write_videofile(str(output_file), fps=24, codec='libx264')
    
    return output_file

# 主界面
def main():
    st.title("自动演讲视频生成器")
    
    # 侧边栏配置
    st.sidebar.header("配置")
    
    # 获取音色列表
    voices = get_voice_list()
    voice_names = [f"{v['ShortName']} - {v['Gender']} - {v['Locale']}" for v in voices]
    
    # 筛选中英文音色
    zh_voices = [v for v in voice_names if 'zh-CN' in v or 'zh-TW' in v]
    en_voices = [v for v in voice_names if 'en-US' in v or 'en-GB' in v]
    
    # 音色选择
    voice_category = st.sidebar.selectbox("选择语言", ["中文", "英文", "其他"])
    
    if voice_category == "中文":
        voice_options = zh_voices
    elif voice_category == "英文":
        voice_options = en_voices
    else:
        voice_options = voice_names
    
    selected_voice = st.sidebar.selectbox("选择音色", voice_options)
    voice_shortname = selected_voice.split(' - ')[0]
    
    # 背景颜色
    bg_color = st.sidebar.color_picker("背景颜色", "#FFFFFF")
    
    # Markdown输入
    st.subheader("输入Markdown内容")
    st.markdown("使用 `---` 分隔不同页面，使用标题 (# ## ###) 组织内容")
    
    default_md = """# 演讲标题

这是第一页的介绍内容

---

## 第二页标题

### 第一个要点
- 要点详细说明1
- 要点详细说明2

### 第二个要点
这是第二个要点的详细内容

---

# 总结页面

## 主要结论
1. 第一个结论
2. 第二个结论"""
    
    md_text = st.text_area("", default_md, height=300)
    
    # 生成按钮
    if st.button("生成视频"):
        with st.spinner("正在生成视频..."):
            # 解析Markdown
            parsed_content = parse_markdown(md_text)
            
            # 创建视频
            output_file = create_video(parsed_content, voice_shortname, bg_color)
            
            # 显示下载链接
            with open(output_file, "rb") as file:
                btn = st.download_button(
                    label="下载视频",
                    data=file,
                    file_name="lecture_video.mp4",
                    mime="video/mp4"
                )
            
            # 显示视频
            st.video(str(output_file))

if __name__ == "__main__":
    main()
