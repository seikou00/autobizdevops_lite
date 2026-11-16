# -*- coding: utf-8 -*-
"""
Git 提交封装脚本
用法: python git-commit.py --card-no Z991820-11214 --message 添加禁用子查询约束
       python git-commit.py -c Z991820-11214 -m 添加禁用子查询约束
"""
import re
import sys
import subprocess
import argparse
from typing import Tuple


def validate_card_no(card_no: str) -> Tuple[bool, str]:
    """校验卡片编号格式"""
    if not card_no:
        return False, "卡片编号不能为空"

    # 格式: Z开头 + 数字 + - + 数字
    pattern = r'^Z[0-9]+-[0-9]+$'
    if not re.match(pattern, card_no):
        return False, f"卡片编号格式不正确，正确格式: Z<机构号>-<序号> (例如: Z991820-11214)"

    return True, ""


def validate_message(message: str) -> Tuple[bool, str]:
    """校验提交信息"""
    if not message or not message.strip():
        return False, "提交信息不能为空"

    if '"' in message or "'" in message:
        return False, "提交信息不能包含引号"

    return True, ""


def git_add_and_commit(full_message: str) -> Tuple[bool, str]:
    """执行git add 和 git commit"""
    try:
        # git add -A
        result1 = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )

        if result1.returncode != 0:
            return False, f"git add 失败: {result1.stderr}"

        # git commit
        result2 = subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "commit", "-m", full_message],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )

        if result2.returncode != 0:
            return False, f"git commit 失败: {result2.stderr}"

        return True, result2.stdout

    except Exception as e:
        return False, f"执行出错: {str(e)}"


def main():
    # 创建参数解析器
    parser = argparse.ArgumentParser(
        description='Git 提交封装脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python git-commit.py --card-no Z991820-11214 --message 添加禁用子查询约束
  python git-commit.py -c Z991820-11214 -m 修复BUG
  python git-commit.py --card-no Z991820-11214 --message "添加新功能"
        '''
    )

    # 添加参数
    parser.add_argument(
        '-c', '--card-no',
        type=str,
        required=True,
        help='卡片编号 (例如: Z991820-11214)'
    )

    parser.add_argument(
        '-m', '--message',
        type=str,
        required=True,
        help='提交信息'
    )

    # 解析参数
    args = parser.parse_args()

    card_no = args.card_no.strip()
    message = args.message.strip()

    # 校验卡片编号
    valid, error = validate_card_no(card_no)
    if not valid:
        print(f"❌ 错误: {error}")
        sys.exit(1)

    # 校验提交信息
    valid, error = validate_message(message)
    if not valid:
        print(f"❌ 错误: {error}")
        sys.exit(1)

    # 构建完整提交信息
    full_message = f"{card_no} #comment {message} [cmbdevclaw]"

    print("📝 正在提交...")
    print(f"   卡片编号: {card_no}")
    print(f"   提交信息: {message}")
    print(f"   完整提交: {full_message}")
    print()

    # 执行提交
    success, result = git_add_and_commit(full_message)

    if success:
        print("✅ 提交成功!")
    else:
        print(f"❌ 提交失败: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()