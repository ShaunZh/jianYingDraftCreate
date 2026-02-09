# Coze → 剪映草稿生成工具 - 使用说明

## 快速开始

### 1. 运行工具

```bash
python3 coze_draft.py
```

### 2. 粘贴 JSON 数据

从 Coze 工作流复制输出的 JSON 数据，粘贴到终端，然后按 `Ctrl+D` 结束输入。

### 3. 等待生成

工具会自动：
- 下载/缓存图片和音频
- 创建剪映草稿
- 导入字幕和样式

### 4. 打开剪映

在剪映中查找草稿，标题格式：`[topic~hook_type~output_language~时间戳]`

## 新特性：智能缓存机制

### 问题背景

多次生成草稿时，相同的图片/音频 URL 会被重复下载，浪费时间和带宽。

### 解决方案

工具现在会自动缓存所有下载的资源到 `coze_cache/media/` 目录：

```
第一次生成草稿:
  获取 10 张图片...
    [1/10] OK          ← 从网络下载
    [2/10] OK
  统计: 0 缓存 / 10 下载

第二次生成草稿（相同内容）:
  获取 10 张图片...
    [1/10] CACHED      ← 从缓存复制（秒级完成）
    [2/10] CACHED
  统计: 10 缓存 / 0 下载
```

### 优势

- ⚡ **速度提升**：缓存命中时几乎瞬间完成
- 💾 **节省带宽**：相同 URL 只下载一次
- 🔒 **离线友好**：原始 URL 失效后仍可从缓存生成草稿
- 🎯 **零配置**：自动管理，无需手动操作

### 缓存管理

**查看缓存：**
```bash
ls -lh coze_cache/media/
```

**清理旧缓存：**
```bash
# 模拟运行（不会实际删除）
python3 clean_cache.py 30 --dry-run

# 删除超过 30 天的缓存
python3 clean_cache.py 30

# 删除超过 7 天的缓存
python3 clean_cache.py 7
```

详细说明请查看 [CACHE_DESIGN.md](./CACHE_DESIGN.md)

## JSON 数据格式要求

### 必需字段

```json
{
  "topic": "视频主题",
  "hook_type": "反常识",
  "output_language": "zh",
  "image_list": "[{...}]",
  "audio_list": "[{...}]",
  "text_cap": [...],
  "text_timelines": [...]
}
```

### 草稿标题规则

生成的草稿标题格式：`[topic~hook_type~output_language~时间戳]`

例如：
- `空军也必带的3样东西~反常识~zh~1770607901`
- `空军也能很骄傲- 空军？我这是在'打窝养鱼'~反常识~en~1770607902`

特殊字符会自动清理：
- `:` → `-`
- `?` → `？`（全角）
- `/` → `-`
- 其他非法字符也会被替换为合法字符

## 项目结构

```
.
├── coze_draft.py           # 主程序
├── clean_cache.py          # 缓存清理工具
├── CACHE_DESIGN.md         # 缓存机制设计文档
├── requirements.md         # 项目背景和需求
├── coze_cache/             # 缓存目录（自动创建）
│   └── media/             # 媒体文件缓存
│       ├── {hash}.png     # 图片缓存
│       └── {hash}.mp3     # 音频缓存
├── temp/                  # 临时草稿目录
│   └── {draft_name}/      # 构建中的草稿
└── template/              # 剪映模板文件
    ├── draft_meta_info.json
    ├── platform_config.json
    └── ...
```

## 常见问题

### Q: 缓存会占用多少空间？
A: 取决于素材数量和质量。估算：
- 10 个草稿（每个 10 张图 + 10 段音频）≈ 100-500 MB
- 建议定期清理超过 30 天的缓存

### Q: 如何强制重新下载某个资源？
A: 删除对应的缓存文件：
```bash
# 查找缓存文件
ls coze_cache/media/

# 删除特定文件
rm coze_cache/media/{hash}.png
```

### Q: 草稿生成失败怎么办？
A: 检查以下几点：
1. 剪映草稿目录是否存在：`~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft`
2. JSON 数据是否完整
3. 网络是否正常（首次下载时）
4. 查看错误信息

### Q: 如何批量生成草稿？
A: 可以使用脚本批量处理：
```bash
# 方法 1: 管道输入
cat dataSource/data3.json | python3 coze_draft.py

# 方法 2: 循环处理
for file in dataSource/*.json; do
  cat "$file" | python3 coze_draft.py
done
```

### Q: 缓存的 hash 文件名如何对应原始 URL？
A: 使用 MD5 hash：
```python
import hashlib
url = "https://example.com/image.png"
hash_key = hashlib.md5(url.encode('utf-8')).hexdigest()
# 缓存文件名: coze_cache/media/{hash_key}.png
```

## 技术架构

### 核心优化

1. **全局缓存机制**：避免重复下载
2. **智能文件名清理**：确保跨平台兼容
3. **兜底策略**：图片缺失时自动使用备用方案
4. **原子化草稿创建**：先在临时目录构建，完成后移入剪映目录

### 设计原则（Linus 式）

- **简洁优先**：文件系统即数据库，无需额外配置
- **消除特殊情况**：统一的缓存逻辑处理所有下载
- **数据结构正确**：URL → hash → 文件的自然映射
- **零维护成本**：缓存独立存在，草稿删除不影响缓存

详见 [CACHE_DESIGN.md](./CACHE_DESIGN.md) 了解设计思路。

## 版本历史

### v2.1 (当前)
- ✨ 新增：全局 URL 缓存机制
- ✨ 新增：缓存清理工具 `clean_cache.py`
- 🎯 优化：草稿标题使用 `[topic~hook_type~output_language~时间戳]` 格式
- 🛡️ 增强：文件名非法字符清理
- 📊 改进：下载进度显示缓存命中状态

### v2.0
- 自定义草稿标题格式
- 文件名安全性增强

### v1.0
- 基础草稿生成功能
- 图片/音频下载
- 字幕导入

## 许可证

MIT

---

**"Talk is cheap. Show me the code."** - Linus Torvalds
