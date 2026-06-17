#!/bin/bash
# Smile Code Agent CLI
# 自动激活 venv 并启动 CLI

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# 检查后端是否已在运行
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "Starting backend server..."
    python -m src.main &
    BACKEND_PID=$!
    # 等待就绪
    for i in $(seq 1 20); do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
fi

python cli.py

# 清理
if [ -n "$BACKEND_PID" ]; then
    kill $BACKEND_PID 2>/dev/null
fi
