# 缓存机制设计文档

## 问题

多次生成剪映草稿时，相同的图片/音频 URL 被重复下载，导致：
- 浪费时间（每次等待网络下载）
- 浪费带宽（重复下载相同内容）
- 离线不可用（URL 失效后无法重新生成）

## 解决方案

### 核心思想

**"文件系统就是数据库"** - 全局 URL 缓存

```
URL → MD5 Hash → coze_cache/media/{hash}.{ext}
```

### 工作流程

```python
# 步骤 1: 检查草稿目录
if target_path.exists():
    return "exists"

# 步骤 2: 检查缓存目录
cache_path = coze_cache/media/{md5(url)}.{ext}
if cache_path.exists():
    copy(cache_path → target_path)
    return "cached"  # 秒级完成

# 步骤 3: 下载并缓存
download(url → cache_path)
copy(cache_path → target_path)
return "downloaded"
```

### 为什么用 MD5？

- **固定长度**：32 字符，不受 URL 长度影响
- **无冲突**：相同 URL 必定生成相同 hash
- **合法文件名**：纯十六进制，跨平台兼容
- **性能足够**：无需密码学强度，只需快速映射

## 效果对比

### 首次生成（无缓存）
```
获取 10 张图片...
  [1/10] OK          ← 网络下载
  [2/10] OK
  统计: 0 缓存 / 10 下载

总耗时: ~30 秒
```

### 二次生成（有缓存）
```
获取 10 张图片...
  [1/10] CACHED      ← 缓存复制
  [2/10] CACHED
  统计: 10 缓存 / 0 下载

总耗时: ~2 秒  ⚡ 提升 15 倍
```

## 优势

### vs 草稿记录方案

| 维度 | 全局缓存（当前） | 草稿记录（备选） |
|-----|----------------|----------------|
| 复杂度 | 低（1个函数） | 高（数据库+清理逻辑） |
| 可靠性 | 高（独立存在） | 低（需同步草稿） |
| 维护 | 零维护成本 | 需定期清理记录 |

### Linus 式"好品味"

✅ **简洁**：文件系统 = 数据库，零配置  
✅ **无特殊情况**：统一的缓存逻辑处理所有下载  
✅ **数据结构正确**：URL → hash → 文件的自然映射  
✅ **零维护**：缓存独立于草稿，草稿删除不影响缓存

## 使用

### 自动缓存（无需配置）

```bash
python3 coze_draft.py
# 第一次运行：下载并缓存
# 第二次运行：从缓存复制（秒级）
```

### 清理缓存（可选）

```bash
# 清理超过 30 天的缓存
python3 clean_cache.py 30

# 模拟运行（不实际删除）
python3 clean_cache.py 30 --dry-run

# 手动清理所有缓存
rm -rf coze_cache/media/
```

### 查看缓存

```bash
# 查看缓存文件
ls -lh coze_cache/media/

# 查看缓存大小
du -sh coze_cache/media/
```

## 常见问题

**Q: 缓存会无限增长吗？**  
A: 会，但速度很慢。建议定期清理超过 30 天的缓存。估算：10 个草稿（每个 10 张图 + 10 段音频）约 100-500 MB。

**Q: URL 参数变化怎么办？**  
A: 不同 URL（即使内容相同）会被视为不同资源。这是权衡的结果：**简单 > 完美**。

**Q: 如何强制重新下载？**  
A: 删除对应缓存文件：`rm coze_cache/media/{hash}.png`

**Q: 网络资源更新后缓存会过期吗？**  
A: 不会自动过期。如需强制更新，手动删除对应缓存文件。

## 技术细节

### URL → 文件名映射示例

```python
import hashlib

url = "https://s.coze.cn/t/6zJU7Bx0YBc/"
hash_key = hashlib.md5(url.encode('utf-8')).hexdigest()
# → "164f69096378d740b19f8c68114b4c37"

cache_file = f"coze_cache/media/{hash_key}.png"
# → "coze_cache/media/164f69096378d740b19f8c68114b4c37.png"
```

### 代码实现

**新增函数：**
```python
def url_to_cache_key(url: str) -> str:
    return hashlib.md5(url.encode('utf-8')).hexdigest()

def get_cached_or_download(url, target_path, file_type) -> (bool, str):
    # 返回 (成功与否, 状态: "cached"/"downloaded"/"failed")
    ...
```

**修改内容：**
- `coze_draft.py`：新增 `CACHE_DIR` 配置，重构下载逻辑
- 下载输出：显示 `CACHED` / `OK` 状态
- 统计信息：`X 缓存 / Y 下载 / Z 兜底`

---

**"Simplicity is the ultimate sophistication."**  
**"Talk is cheap. Show me the code."**
