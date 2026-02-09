#!/usr/bin/env python3
"""
清理缓存脚本：删除超过指定天数未使用的缓存文件
"""
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
CACHE_DIR = SCRIPT_DIR / "coze_cache" / "media"

def clean_cache(days: int = 30, dry_run: bool = False):
    """
    清理超过指定天数未访问的缓存文件
    
    Args:
        days: 天数阈值（默认 30 天）
        dry_run: 模拟运行，不实际删除
    """
    if not CACHE_DIR.exists():
        print(f"缓存目录不存在: {CACHE_DIR}")
        return
    
    now = time.time()
    threshold = days * 24 * 3600  # 天数 → 秒
    
    files = list(CACHE_DIR.glob("*"))
    if not files:
        print("缓存目录为空")
        return
    
    print(f"缓存目录: {CACHE_DIR}")
    print(f"文件总数: {len(files)}")
    print(f"清理阈值: 超过 {days} 天未使用")
    print()
    
    to_delete = []
    total_size = 0
    delete_size = 0
    
    for f in files:
        if not f.is_file():
            continue
        
        size = f.stat().st_size
        mtime = f.stat().st_mtime
        age = now - mtime
        total_size += size
        
        if age > threshold:
            to_delete.append((f, age, size))
            delete_size += size
    
    print(f"【分析结果】")
    print(f"  缓存总大小: {total_size / 1024 / 1024:.2f} MB")
    print(f"  待删除文件: {len(to_delete)} 个")
    print(f"  待删除大小: {delete_size / 1024 / 1024:.2f} MB")
    print()
    
    if not to_delete:
        print("无需清理")
        return
    
    if dry_run:
        print("【模拟运行 - 不会实际删除】")
        for f, age, size in to_delete[:5]:  # 只显示前 5 个
            days_old = age / 86400
            print(f"  会删除: {f.name} ({size / 1024:.1f} KB, {days_old:.1f} 天前)")
        if len(to_delete) > 5:
            print(f"  ... 还有 {len(to_delete) - 5} 个文件")
    else:
        confirm = input(f"确认删除 {len(to_delete)} 个文件? (yes/n): ")
        if confirm.lower() == 'yes':
            for f, age, size in to_delete:
                f.unlink()
            print(f"✓ 已删除 {len(to_delete)} 个文件，释放 {delete_size / 1024 / 1024:.2f} MB")
        else:
            print("取消删除")


if __name__ == "__main__":
    import sys
    
    days = 30
    dry_run = False
    
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print(f"用法: {sys.argv[0]} [天数] [--dry-run]")
            sys.exit(1)
    
    if "--dry-run" in sys.argv:
        dry_run = True
    
    clean_cache(days, dry_run)
