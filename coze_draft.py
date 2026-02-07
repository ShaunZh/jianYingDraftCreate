#!/usr/bin/env python3
"""
Coze → 剪映(JianYing) 草稿生成工具
核心策略: 从可用草稿中只复制辅助/格式文件, draft_content.json 完全重新生成
"""
import json
import os
import sys
import time
import shutil
import uuid
import requests
from pathlib import Path

import pyJianYingDraft as draft
from pyJianYingDraft import trange
from pyJianYingDraft.script_file import ScriptFile

# ================= 配置 =================
HOME = Path.home()
JIANYING_DRAFT_ROOT = HOME / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"

# 已知可用的模板草稿 (用于提取 platform 等格式信息, 以及 draft_meta_info.json)
TEMPLATE_DRAFT_NAME = "dcdc02af-9f25-46c7-af1a-ac4bf2cf3af9"

DOWNLOAD_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

# 只从模板复制这些文件/目录 (不复制包含旧内容数据的文件)
COPY_FILES = [
    "draft_meta_info.json",         # 加密的元信息, 让剪映能识别草稿
    "draft_cover.jpg",              # 封面图
    "draft_local_cover.jpg",        # 本地封面图
    "draft_biz_config.json",        # 业务配置
    "draft_agency_config.json",     # 代理配置
    "draft_virtual_store.json",     # 虚拟存储
    "performance_opt_info.json",    # 性能优化信息
    "attachment_editing.json",      # 编辑附件
    "attachment_pc_common.json",    # PC通用附件
]
COPY_DIRS = [
    "draft_settings",
    "common_attachment",
]
# 创建这些空目录 (剪映可能需要它们存在)
EMPTY_DIRS = [
    "adjust_mask",
    "matting",
    "qr_upload",
    "smart_crop",
    "subdraft",
    "Resources",
]


# ================= 工具函数 =================

def safe_parse(data):
    """处理可能被字符串化的 JSON 字段"""
    if isinstance(data, (list, dict)):
        return data
    if isinstance(data, str):
        try:
            return safe_parse(json.loads(data))
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def download(url, save_path):
    """下载文件, 返回是否成功"""
    save_path = Path(save_path)
    if save_path.exists() and save_path.stat().st_size > 0:
        return True
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT},
                         stream=True, timeout=DOWNLOAD_TIMEOUT, allow_redirects=True)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return save_path.exists() and save_path.stat().st_size > 0
    except Exception as e:
        print(f"  下载失败: {e}")
    return False


def _srt_time(us):
    """微秒 → SRT 时间格式"""
    ms = int(us / 1000)
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def copy_template_files(template_path, project_path):
    """从模板草稿中只复制辅助文件, 不复制任何内容数据"""
    project_path.mkdir(parents=True, exist_ok=True)

    # 复制单个文件
    for fn in COPY_FILES:
        src = template_path / fn
        if src.exists():
            shutil.copy2(str(src), str(project_path / fn))

    # 复制目录
    for dn in COPY_DIRS:
        src = template_path / dn
        if src.exists():
            dst = project_path / dn
            if src.is_dir():
                shutil.copytree(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))

    # 创建空目录
    for dn in EMPTY_DIRS:
        (project_path / dn).mkdir(parents=True, exist_ok=True)


# ================= 主逻辑 =================

def main():
    # ─── 1. 读取输入 ───
    print("请粘贴 Coze JSON 数据, 按 Ctrl+D (macOS) 结束:")
    raw = sys.stdin.read().strip()
    if not raw:
        print("错误: 没有输入数据")
        return

    data = json.loads(raw)

    # ─── 2. 解析字段 ───
    images = safe_parse(data.get("image_list", []))
    audios = safe_parse(data.get("audio_list", []))
    captions = data.get("text_cap", [])
    text_timelines = data.get("text_timelines", [])

    print(f"解析完成: {len(images)} 图片, {len(audios)} 音频, {len(captions)} 字幕")

    # ─── 3. 检查环境 ───
    if not JIANYING_DRAFT_ROOT.exists():
        print(f"错误: 剪映草稿目录不存在: {JIANYING_DRAFT_ROOT}")
        return

    template_path = JIANYING_DRAFT_ROOT / TEMPLATE_DRAFT_NAME
    template_content_path = template_path / "draft_content.json"
    if not template_path.exists() or not template_content_path.exists():
        print(f"错误: 模板草稿不存在或缺少 draft_content.json: {template_path}")
        return

    # ─── 4. 创建新草稿目录 (只复制辅助文件, 不复制内容数据) ───
    project_name = f"Coze_{int(time.time())}"
    project_path = JIANYING_DRAFT_ROOT / project_name

    print(f"创建草稿: {project_name}")
    copy_template_files(template_path, project_path)
    print("  已复制模板辅助文件 (不含旧内容数据)")

    # ─── 5. 创建素材目录并下载 ───
    materials_dir = project_path / "materials"
    materials_dir.mkdir(parents=True, exist_ok=True)

    downloaded_images = []
    if images:
        print(f"下载 {len(images)} 张图片...")
        for i, img in enumerate(images):
            url = img.get("image_url", "")
            if not url:
                continue
            local = materials_dir / f"image_{i}.png"
            if download(url, local):
                print(f"  [{i+1}/{len(images)}] OK")
                downloaded_images.append((i, img, local))
            else:
                print(f"  [{i+1}/{len(images)}] FAIL - 跳过")

    downloaded_audios = []
    if audios:
        print(f"下载 {len(audios)} 段音频...")
        for i, aud in enumerate(audios):
            url = aud.get("audio_url", "")
            if not url:
                continue
            local = materials_dir / f"audio_{i}.mp3"
            if download(url, local):
                print(f"  [{i+1}/{len(audios)}] OK")
                downloaded_audios.append((i, aud, local))
            else:
                print(f"  [{i+1}/{len(audios)}] FAIL - 跳过")

    # ─── 6. 用 pyJianYingDraft 构建 draft_content.json ───
    # 创建 ScriptFile, 然后用模板的 content 做基底 (继承 platform 等字段)
    script = ScriptFile(1920, 1080)

    # 读取模板的 draft_content.json, 提取关键格式字段
    with open(template_content_path, "r", encoding="utf-8") as f:
        template_content = json.load(f)

    # 将模板的关键字段合并到 pyJianYingDraft 的默认 content 中
    script.content["platform"] = template_content["platform"]
    script.content["last_modified_platform"] = template_content["last_modified_platform"]
    script.content["color_space"] = template_content.get("color_space", -1)
    script.content["render_index_track_mode_on"] = template_content.get("render_index_track_mode_on", True)
    for key in ["lyrics_effects", "is_drop_frame_timecode", "path"]:
        if key in template_content:
            script.content[key] = template_content[key]

    # 设置新的 ID 和时间戳
    new_content_id = str(uuid.uuid4())
    script.content["id"] = new_content_id
    script.content["create_time"] = int(time.time())
    script.content["update_time"] = int(time.time())

    # 设置保存路径
    draft_content_file = project_path / "draft_content.json"
    script.save_path = str(draft_content_file)
    script.duration = 0

    # ─── 7. 添加视频轨道和片段 ───
    if downloaded_images:
        script.add_track(draft.TrackType.video, "images")
        for i, img, local in downloaded_images:
            start = int(img.get("start", 0))
            end = int(img.get("end", 0))
            duration = end - start if end > start else 3000000
            seg = draft.VideoSegment(str(local), trange(start, duration))
            script.add_segment(seg, "images")

    # ─── 8. 添加音频轨道和片段 ───
    if downloaded_audios:
        script.add_track(draft.TrackType.audio, "audios")
        for i, aud, local in downloaded_audios:
            start = int(aud.get("start", 0))
            duration = int(aud.get("duration", 0))
            if duration <= 0:
                end = int(aud.get("end", 0))
                duration = end - start if end > start else 3000000
            seg = draft.AudioSegment(str(local), trange(start, duration))
            script.add_segment(seg, "audios")

    # ─── 9. 生成字幕并导入到草稿 ───
    if captions and text_timelines:
        srt_path = project_path / "captions.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, text in enumerate(captions):
                if i < len(text_timelines):
                    t = text_timelines[i]
                    s, e = int(t["start"]), int(t["end"])
                    f.write(f"{i+1}\n")
                    f.write(f"{_srt_time(s)} --> {_srt_time(e)}\n")
                    f.write(f"{text}\n\n")
        print(f"字幕文件: captions.srt ({len(captions)} 条)")

        # 使用 pyJianYingDraft 的 import_srt 将字幕导入到文本轨道
        script.import_srt(str(srt_path), "subtitles")
        print(f"  已导入字幕到文本轨道 ({len(captions)} 条)")

    # ─── 10. 保存 ───
    script.save()
    print("draft_content.json 已生成")

    # ─── 11. 生成 draft_info.json (剪映必需, 用 draft_content.json 的内容) ───
    shutil.copy2(str(draft_content_file), str(project_path / "draft_info.json"))
    print("draft_info.json 已生成")

    # ─── 12. 写 timeline_layout.json ───
    timeline_layout = {
        "dockItems": [{
            "dockIndex": 0,
            "ratio": 1,
            "timelineIds": [new_content_id],
            "timelineNames": ["时间线01"]
        }],
        "layoutOrientation": 1
    }
    with open(project_path / "timeline_layout.json", "w", encoding="utf-8") as f:
        json.dump(timeline_layout, f, ensure_ascii=False, indent=2)

    # ─── 13. 验证 ───
    print(f"\n验证:")
    with open(draft_content_file, "r") as f:
        dc = json.load(f)
    print(f"  platform.os: {dc['platform']['os']}")
    print(f"  duration: {dc['duration']}")
    print(f"  tracks: {len(dc['tracks'])}")
    for t in dc['tracks']:
        print(f"    {t['type']}: {len(t['segments'])} segments")
    print(f"  videos: {len(dc['materials']['videos'])}")
    print(f"  audios: {len(dc['materials']['audios'])}")
    print(f"  texts: {len(dc['materials']['texts'])}")
    if dc['materials']['videos']:
        p = dc['materials']['videos'][0]['path']
        print(f"  首个视频路径: {p}")

    print(f"\n草稿已保存到: {project_path}")
    print(f"请打开【剪映】查找草稿: {project_name}")


if __name__ == "__main__":
    main()
