#!/bin/bash
# keep_awake.sh - 防止 Mac 在喚醒後 2 分鐘內進入睡眠模式
# 使用方法: ./keep_awake.sh

echo "已啟動：防止系統休眠 (2 分鐘)..."
# -d: 保持螢幕開啟 (Prevent display sleep)
# -i: 保持系統開啟 (Prevent system idle sleep)
# -t 120: 持續 120 秒 (2 分鐘)
caffeinate -di -t 120
echo "2 分鐘已過，恢復預設休眠邏輯。"
