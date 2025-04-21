import streamlit as st

st.set_page_config(page_title="Markdown 分页预览", layout="centered")

st.title("📄 Markdown 分页预览器")

st.markdown("请输入带有 `---` 分隔的 Markdown 内容，每一段将被视为一个页面：")

default_md = """
欢迎使用视频生成工具！

> 这是一段配音内容

---

这是第二页内容，可以继续添加内容。

> 第二页的配音内容
"""

markdown_input = st.text_area("Markdown 输入", height=400, value=default_md)

if markdown_input.strip():
    pages = [p.strip() for p in markdown_input.split('---') if p.strip()]
    st.success(f"共分为 {len(pages)} 页")

    for i, page in enumerate(pages, 1):
        st.markdown(f"### 第 {i} 页")
        st.markdown(page, unsafe_allow_html=True)
        st.divider()
