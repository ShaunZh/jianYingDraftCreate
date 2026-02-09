#!/usr/bin/env python3
"""
Coze → 剪映(JianYing) 草稿生成工具
完全自包含: 所有模板文件保存在 ./template/ 目录中, 不依赖外部草稿
"""
import json
import os
import base64
import sys
import time
import shutil
import uuid
import requests
from pathlib import Path

import pyJianYingDraft as draft
from pyJianYingDraft import trange
from pyJianYingDraft.script_file import ScriptFile
from pyJianYingDraft.text_segment import TextStyle, TextBorder, TextShadow, TextSegment

# ================= 配置 =================
HOME = Path.home()
SCRIPT_DIR = Path(__file__).parent.resolve()
TEMPLATE_DIR = SCRIPT_DIR / "template"

# 剪映(中国内地版)草稿路径
JIANYING_DRAFT_ROOT = HOME / "Movies/JianyingPro/User Data/Projects/com.lveditor.draft"

DOWNLOAD_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

# 画布尺寸（手机竖屏 9:16）
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

# 全白背景（'#RRGGBBAA'）
BACKGROUND_COLOR = "#FFFFFFFF"

# 字幕样式（尽量贴近你截图里的蓝色描边效果）
SUBTITLE_FONT_SIZE = 8.0
# 字体填充色：浅蓝（RGB 0~1）
SUBTITLE_FILL_RGB = (0.60, 0.87, 1.00)
# 描边：白色
SUBTITLE_BORDER_RGB = (1.00, 1.00, 1.00)
# 描边宽度（0~100，值越大边越粗）
SUBTITLE_BORDER_WIDTH = 55.0
# 阴影（可选：更接近“预设”观感；不想要可将 SUBTITLE_SHADOW_ALPHA 设为 0）
SUBTITLE_SHADOW_ALPHA = 0.35
SUBTITLE_SHADOW_RGB = (0.00, 0.00, 0.00)
SUBTITLE_SHADOW_DIFFUSE = 18.0
SUBTITLE_SHADOW_DISTANCE = 6.0
SUBTITLE_SHADOW_ANGLE = -45.0

# 从 template/ 复制到新草稿的文件
TEMPLATE_FILES = [
    "draft_meta_info.json",
    "draft_biz_config.json",
    "draft_agency_config.json",
    "draft_virtual_store.json",
    "performance_opt_info.json",
    "attachment_editing.json",
    "attachment_pc_common.json",
    "draft_settings",
]
TEMPLATE_DIRS = [
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

def to_int_us(value, default: int = 0) -> int:
    """将可能为 int/float/数字字符串(含小数) 的时间统一转为微秒整数。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            return int(s)
        except ValueError:
            try:
                return int(round(float(s)))
            except ValueError:
                return default
    try:
        return int(round(float(value)))
    except Exception:
        return default


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


_WHITE_1X1_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
    "ASsJTYQAAAAASUVORK5CYII="
)


def ensure_white_png(path: Path) -> Path:
    """创建一个白底 1x1 PNG 占位图（若不存在）。"""
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(base64.b64decode(_WHITE_1X1_PNG_B64))
    return path


def ensure_copy(src: Path, dst: Path) -> bool:
    """将 src 复制到 dst（dst 不存在/为空时），返回是否成功。"""
    src = Path(src)
    dst = Path(dst)
    if dst.exists() and dst.stat().st_size > 0:
        return True
    if not src.exists() or src.stat().st_size <= 0:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    return dst.exists() and dst.stat().st_size > 0


def _srt_time(us):
    """微秒 → SRT 时间格式"""
    ms = int(us / 1000)
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    清理文件名/目录名中的非法字符，确保符合 macOS 和剪映要求。
    
    macOS 限制:
    - 不能包含 `/` (路径分隔符)
    - 不能包含 `:` (虽然技术上可以，但会被系统转换为 `/`)
    - 总长度不超过 255 字节
    
    剪映草稿命名建议:
    - 避免特殊字符 `<>:"|?*\` 等
    - 保持可读性
    """
    if not name:
        return "untitled"
    
    # 替换/删除非法字符
    illegal_chars = {
        '/': '-',   # macOS 路径分隔符
        ':': '-',   # macOS 特殊字符
        '<': '《',  # 全角替换，保持可读性
        '>': '》',
        '"': "'",   # 单引号替换双引号
        '|': '-',
        '?': '？',  # 全角问号
        '*': '✱',
        '\\': '-',
        '\n': ' ',  # 换行替换为空格
        '\r': ' ',
        '\t': ' ',
    }
    
    for char, replacement in illegal_chars.items():
        name = name.replace(char, replacement)
    
    # 移除首尾空格和点号（macOS 不建议）
    name = name.strip('. ')
    
    # 限制长度（UTF-8 编码，macOS 限制 255 字节）
    while len(name.encode('utf-8')) > max_length:
        name = name[:-1]
    
    return name or "untitled"


def generate_draft_title(data: dict) -> str:
    """
    从 Coze JSON 数据生成草稿标题。
    格式: [topic~hook_type~output_language~时间戳]
    """
    topic = data.get("topic", "").strip()
    hook_type = data.get("hook_type", "").strip()
    output_language = data.get("output_language", "").strip()
    timestamp = int(time.time())
    
    # 清理每个字段
    topic_clean = sanitize_filename(topic, max_length=80) if topic else "untitled"
    hook_type_clean = sanitize_filename(hook_type, max_length=30) if hook_type else "unknown"
    lang_clean = sanitize_filename(output_language, max_length=10) if output_language else "unknown"
    
    # 拼接标题
    title = f"{topic_clean}~{hook_type_clean}~{lang_clean}~{timestamp}"
    
    # 最终保险：再次清理并限制总长度
    return sanitize_filename(title, max_length=200)


def setup_project(project_path):
    """从本地 template/ 目录初始化新草稿项目"""
    project_path.mkdir(parents=True, exist_ok=True)

    # 复制模板文件
    for fn in TEMPLATE_FILES:
        src = TEMPLATE_DIR / fn
        if src.exists():
            shutil.copy2(str(src), str(project_path / fn))

    # 复制模板目录
    for dn in TEMPLATE_DIRS:
        src = TEMPLATE_DIR / dn
        if src.exists():
            dst = project_path / dn
            if src.is_dir():
                shutil.copytree(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))

    # 创建空目录
    for dn in EMPTY_DIRS:
        (project_path / dn).mkdir(parents=True, exist_ok=True)


def load_platform_config():
    """从 template/platform_config.json 加载平台格式字段"""
    config_path = TEMPLATE_DIR / "platform_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"缺少配置文件: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ================= 主逻辑 =================

def main():
    # ─── 1. 检查 template/ 目录 ───
    if not TEMPLATE_DIR.exists():
        print(f"错误: 模板目录不存在: {TEMPLATE_DIR}")
        print("请确保 template/ 目录包含必要的模板文件")
        return

    # ─── 2. 读取输入 ───
    print("请粘贴 Coze JSON 数据, 按 Ctrl+D (macOS) 结束:")
    raw = sys.stdin.read().strip()
    if not raw:
        print("错误: 没有输入数据")
        return

    data = json.loads(raw)

    # ─── 3. 解析字段 ───
    images = safe_parse(data.get("image_list", []))
    audios = safe_parse(data.get("audio_list", []))
    captions = data.get("text_cap", [])
    text_timelines = data.get("text_timelines", [])

    print(f"解析完成: {len(images)} 图片, {len(audios)} 音频, {len(captions)} 字幕")

    # ─── 4. 检查剪映草稿目录 ───
    if not JIANYING_DRAFT_ROOT.exists():
        print(f"错误: 剪映草稿目录不存在: {JIANYING_DRAFT_ROOT}")
        return

    # ─── 5. 在临时目录中准备草稿 (避免剪映监控到不完整的草稿而删除) ───
    project_name = generate_draft_title(data)
    # 先在项目目录下的 temp/ 中构建, 最后整体移入剪映草稿目录
    project_path = SCRIPT_DIR / "temp" / project_name

    print(f"创建草稿: {project_name}")
    setup_project(project_path)

    # ─── 6. 下载素材 ───
    materials_dir = project_path / "materials"
    materials_dir.mkdir(parents=True, exist_ok=True)

    downloaded_images = []
    if images:
        print(f"下载 {len(images)} 张图片...")
        # bg_image 作为首张兜底（如果第一张图失败/缺失）
        bg_list = safe_parse(data.get("bg_image", []))
        bg_local = None
        if isinstance(bg_list, list) and bg_list:
            bg_url = (bg_list[0] or {}).get("image_url", "")
            if bg_url:
                candidate = materials_dir / "bg_fallback.png"
                if download(bg_url, candidate):
                    bg_local = candidate

        placeholder_local = ensure_white_png(materials_dir / "placeholder.png")
        prev_ok_local = None

        for i, img in enumerate(images):
            url = img.get("image_url", "")
            local = materials_dir / f"image_{i}.png"
            ok = False
            if url:
                ok = download(url, local)

            if ok:
                print(f"  [{i+1}/{len(images)}] OK")
                prev_ok_local = local
            else:
                # 兜底策略：上一张成功图 > bg_image > 白底占位图
                if not url:
                    reason = "empty image_url"
                else:
                    reason = "download failed"

                fallback_src = prev_ok_local or bg_local or placeholder_local
                fallback_label = (
                    "prev_image" if prev_ok_local else
                    ("bg_image" if bg_local else "placeholder")
                )

                if ensure_copy(fallback_src, local):
                    print(f"  [{i+1}/{len(images)}] FALLBACK ({reason}) -> {fallback_label}")
                else:
                    # 极端情况：兜底源也不可用，则强制写占位图到 local
                    ensure_white_png(local)
                    print(f"  [{i+1}/{len(images)}] FALLBACK ({reason}) -> placeholder (forced)")

            # 不管是否成功下载，都保持时间轴段数一致
            downloaded_images.append((i, img, local))

    downloaded_audios = []
    if audios:
        print(f"下载 {len(audios)} 段音频...")
        for i, aud in enumerate(audios):
            url = aud.get("audio_url", "")
            if not url:
                print(f"  [{i+1}/{len(audios)}] SKIP - empty audio_url")
                continue
            local = materials_dir / f"audio_{i}.mp3"
            if download(url, local):
                print(f"  [{i+1}/{len(audios)}] OK")
                downloaded_audios.append((i, aud, local))
            else:
                print(f"  [{i+1}/{len(audios)}] FAIL - 跳过")

    # ─── 7. 构建 draft_content.json ───
    script = ScriptFile(CANVAS_WIDTH, CANVAS_HEIGHT)

    # 加载平台格式配置
    platform_config = load_platform_config()
    for key, value in platform_config.items():
        script.content[key] = value

    # 设置新的 ID 和时间戳
    new_content_id = str(uuid.uuid4())
    script.content["id"] = new_content_id
    script.content["create_time"] = int(time.time())
    script.content["update_time"] = int(time.time())

    # 设置保存路径
    draft_content_file = project_path / "draft_content.json"
    script.save_path = str(draft_content_file)
    script.duration = 0

    # ─── 8. 添加视频轨道 ───
    if downloaded_images:
        script.add_track(draft.TrackType.video, "images")
        for i, img, local in downloaded_images:
            start = to_int_us(img.get("start", 0))
            end = to_int_us(img.get("end", 0))
            duration = end - start if end > start else 3000000
            seg = draft.VideoSegment(str(local), trange(start, duration))
            # 白色背景填充：竖屏画布下更自然（避免黑边）
            try:
                seg.add_background_filling("color", blur=0.0, color=BACKGROUND_COLOR)
            except Exception:
                pass
            script.add_segment(seg, "images")

    # ─── 9. 添加音频轨道 ───
    if downloaded_audios:
        script.add_track(draft.TrackType.audio, "audios")
        for i, aud, local in downloaded_audios:
            start = to_int_us(aud.get("start", 0))
            duration = to_int_us(aud.get("duration", 0))
            if duration <= 0:
                end = to_int_us(aud.get("end", 0))
                duration = end - start if end > start else 3000000
            seg = draft.AudioSegment(str(local), trange(start, duration))
            script.add_segment(seg, "audios")

    # ─── 10. 生成字幕并导入 ───
    if captions and text_timelines:
        srt_path = project_path / "captions.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, text in enumerate(captions):
                if i < len(text_timelines):
                    t = text_timelines[i]
                    s = to_int_us(t.get("start", 0))
                    e = to_int_us(t.get("end", 0))
                    f.write(f"{i+1}\n")
                    f.write(f"{_srt_time(s)} --> {_srt_time(e)}\n")
                    f.write(f"{text}\n\n")
        print(f"字幕: {len(captions)} 条")
        # 构造一个“样式模板”，让导入的每条字幕继承该样式
        style_ref = TextSegment(
            "template",
            trange(0, 1_000_000),
            style=TextStyle(
                size=SUBTITLE_FONT_SIZE,
                align=1,  # 居中
                auto_wrapping=True,
                color=SUBTITLE_FILL_RGB,
            ),
            border=TextBorder(
                alpha=1.0,
                color=SUBTITLE_BORDER_RGB,
                width=SUBTITLE_BORDER_WIDTH,
            ),
            shadow=TextShadow(
                alpha=SUBTITLE_SHADOW_ALPHA,
                color=SUBTITLE_SHADOW_RGB,
                diffuse=SUBTITLE_SHADOW_DIFFUSE,
                distance=SUBTITLE_SHADOW_DISTANCE,
                angle=SUBTITLE_SHADOW_ANGLE,
            ) if SUBTITLE_SHADOW_ALPHA > 0 else None,
        )
        script.import_srt(str(srt_path), "subtitles", style_reference=style_ref)

    # ─── 11. 保存 draft_content.json ───
    script.save()

    # ─── 12. 生成 draft_info.json (剪映必需) ───
    shutil.copy2(str(draft_content_file), str(project_path / "draft_info.json"))

    # ─── 13. 写 timeline_layout.json ───
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

    # ─── 14. 将完整草稿移入剪映草稿目录 ───
    final_path = JIANYING_DRAFT_ROOT / project_name
    if final_path.exists():
        shutil.rmtree(str(final_path))
    shutil.move(str(project_path), str(final_path))

    # 修复路径: 将 draft_content.json 和 draft_info.json 中的临时路径替换为最终路径
    temp_prefix = str(project_path)
    final_prefix = str(final_path)
    for json_file in ["draft_content.json", "draft_info.json"]:
        fp = final_path / json_file
        if fp.exists():
            with open(fp, "r", encoding="utf-8") as f:
                text = f.read()
            text = text.replace(temp_prefix, final_prefix)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(text)

    project_path = final_path
    draft_content_file = project_path / "draft_content.json"
    print(f"已移入剪映草稿目录")

    # ─── 15. 验证 ───
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

    print(f"\n草稿已保存到: {project_path}")
    print(f"请打开【剪映】查找草稿: {project_name}")


if __name__ == "__main__":
    main()
