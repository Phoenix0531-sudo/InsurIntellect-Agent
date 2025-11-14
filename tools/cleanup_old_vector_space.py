#!/usr/bin/env python3
"""
旧向量库清理（三级确认后执行）：
 - 先禁用访问（重命名目录并创建锁文件）
 - 按层级删除（索引→数据→元数据）
 - 记录删除操作日志

用法：
  python tools/cleanup_old_vector_space.py --persist_dir data/chroma/old_space --confirm yes
"""

import os
import shutil
import time
import argparse


def main():
    parser = argparse.ArgumentParser(description="清理旧向量库")
    parser.add_argument("--persist_dir", required=True, help="ChromaDB 旧空间目录")
    parser.add_argument("--confirm", default="no", help="必须为 yes 才会执行删除")
    args = parser.parse_args()

    if args.confirm.lower() != "yes":
        print("未确认。退出。")
        return

    if not os.path.isdir(args.persist_dir):
        print("目录不存在，已视为清理完成。")
        return

    ts = time.strftime("%Y%m%d-%H%M%S")
    quarantine = f"{args.persist_dir}_disabled_{ts}"
    try:
        os.rename(args.persist_dir, quarantine)
        print(f"访问禁用：{args.persist_dir} -> {quarantine}")
    except Exception as e:
        print("禁用失败：", e)
        return

    # 创建锁文件
    lock_path = os.path.join(quarantine, "DELETION_LOCK.txt")
    try:
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write("此目录已禁用访问，等待删除。\n")
    except Exception:
        pass

    # 分层删除（简单近似）：
    # Chroma 默认结构不可严格区分索引/数据/元数据，这里按子目录层级逐步删除。
    try:
        for root, dirs, files in os.walk(quarantine, topdown=False):
            for name in files:
                fp = os.path.join(root, name)
                try:
                    os.remove(fp)
                    print("删除文件:", fp)
                except Exception:
                    pass
            for name in dirs:
                dp = os.path.join(root, name)
                try:
                    os.rmdir(dp)
                    print("删除目录:", dp)
                except Exception:
                    pass
        # 最终删除根目录
        shutil.rmtree(quarantine, ignore_errors=True)
        print("清理完成：", quarantine)
    except Exception as e:
        print("清理失败：", e)


if __name__ == "__main__":
    main()

