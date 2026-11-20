#!/usr/bin/env python3
"""从剪贴板读她刚发的那句话，直接给出相关情境卡。

这是「微信只读接入」：你自己在微信里复制那句话，这里读剪贴板。
不登录、不代发、不读聊天记录，微信那边看不到任何异常。

用法:
    python scripts/clip.py                 # 读一次剪贴板
    python scripts/clip.py --scene period  # 指定场景
    python scripts/clip.py --watch         # 盯着剪贴板，复制一句就出一次
    python scripts/clip.py --copy          # 顺便把检索到的最相关卡的示例复制回剪贴板
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import index  # noqa: E402


def _windows_clipboard() -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CF_UNICODETEXT = 13

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    if not user32.OpenClipboard(None):
        return ""
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _command_clipboard() -> str:
    """macOS 用 pbpaste，Linux 用 wl-paste 或 xclip。"""
    for cmd in (
        ["pbpaste"],
        ["wl-paste", "--no-newline"],
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    ):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            continue
        if proc.returncode == 0:
            return proc.stdout
    return ""


def read_clipboard() -> str:
    if sys.platform == "win32":
        try:
            return _windows_clipboard()
        except OSError:
            return ""
    return _command_clipboard()


def copy_to_clipboard(text: str) -> bool:
    """--copy：把示例放回剪贴板，方便你改完直接粘进微信。"""
    if sys.platform == "win32":
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                input=text, capture_output=True, text=True, timeout=10,
            )
            return proc.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        try:
            proc = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=5)
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            continue
        if proc.returncode == 0:
            return True
    return False


def looks_like_her(text: str) -> bool:
    """太长的不像是她刚发的一句话，多半是复制了一篇文章。"""
    return 0 < len(text.strip()) <= 300


def show(text: str, cards, top: int, quiet: bool = False) -> None:
    text = " ".join(text.split())
    if not quiet:
        print(f"【她刚发的】{text}\n")
    if not cards:
        print("没找到对得上的卡。先看 data/scenes/，或者跑 python scripts/find.py 把这句话记成缺口。")
        return
    for rank, (score, card) in enumerate(cards, 1):
        print(index.render(card, rank))
        print()
    best = cards[0][0]
    if best < index.WEAK_SCORE:
        print(
            f"（最高分 {best:.1f} 低于 {index.WEAK_SCORE}，可能只是词对上了，别照着卡写。）",
            file=sys.stderr,
        )
    if not quiet:
        print("提醒：卡给的是方向，不是台词。按你自己的说话习惯改一遍再发。")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="从剪贴板读她的话，给出相关情境卡")
    parser.add_argument("--scene", help="限定场景，比如 period / conflict / latenight")
    parser.add_argument("--top", type=int, default=3, help="给几张卡，默认 3")
    parser.add_argument("--watch", action="store_true", help="盯着剪贴板，变了就再出一次")
    parser.add_argument("--copy", action="store_true", help="把最相关那张卡的示例复制回剪贴板")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读，不用剪贴板")
    args = parser.parse_args()

    cards = index.load_cards()
    search = index.Index(cards)

    def handle(text: str) -> None:
        if not text.strip():
            return
        if not looks_like_her(text):
            print(f"（剪贴板里有 {len(text)} 字，不像一句话，跳过）", file=sys.stderr)
            return
        found = search.search(text, top=args.top, scene=args.scene)
        show(text, found, args.top, quiet=args.watch)
        if args.copy and found:
            example = (found[0][1].get("examples") or [{}])[0].get("text", "")
            if example and copy_to_clipboard(example):
                print(f"（已复制到剪贴板：{example}）", file=sys.stderr)

    if args.stdin:
        handle(sys.stdin.read())
        return

    first = read_clipboard()
    if not first.strip():
        print(
            "剪贴板是空的（或者读不到）。在微信里选中她那句话，Ctrl+C，再跑一次。",
            file=sys.stderr,
        )
        return

    handle(first)
    if not args.watch:
        return

    print("\n盯着剪贴板，复制新的一句就会再出一次。Ctrl+C 退出。", file=sys.stderr)
    last = first
    try:
        while True:
            time.sleep(1.0)
            now = read_clipboard()
            if now != last:
                last = now
                handle(now)
    except KeyboardInterrupt:
        print("", file=sys.stderr)


if __name__ == "__main__":
    main()