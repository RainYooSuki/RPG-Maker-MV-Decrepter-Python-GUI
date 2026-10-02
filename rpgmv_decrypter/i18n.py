"""Translations for the desktop GUI (Chinese default, English switchable).

Kept separate from any toolkit so the same table serves the Qt interface now and
any future frontend.  ``tests/test_gui_i18n.py`` asserts that both languages
cover every key, so a forgotten translation fails the suite instead of showing a
raw identifier.
"""

from __future__ import annotations

from typing import Any

__all__ = ["DEFAULT_LANGUAGE", "LANGUAGES", "TEXT", "tr"]

#: Languages the interface can be shown in.  ``zh`` is the default.
LANGUAGES: dict[str, str] = {"zh": "中文", "en": "English"}
DEFAULT_LANGUAGE = "zh"

#: Every user-visible string, keyed by an identifier.
TEXT: dict[str, dict[str, Any]] = {
    # ---- window chrome ------------------------------------------------
    "app_title": {"zh": "RPG Maker MV / MZ 解密工具", "en": "RPG Maker MV/MZ Decrypter"},
    "app_subtitle": {
        "zh": "解密、重新加密与修复 RPG Maker MV / MZ 资源文件",
        "en": "Decrypt, re-encrypt and repair RPG Maker MV / MZ resources",
    },
    "language": {"zh": "语言", "en": "Language"},
    # The "完全离线" (fully offline) badge and its tooltip lived here.  Removed: the
    # tool has no network feature, so the badge advertised the absence of something
    # that was never offered - the user's words were "完全没意义的东西".
    # ---- steps --------------------------------------------------------
    "step_key": {"zh": "1 · 获取密钥", "en": "1 · Get the key"},
    "step_files": {"zh": "2 · 选择文件", "en": "2 · Choose files"},
    "step_run": {"zh": "3 · 开始处理", "en": "3 · Run"},
    "step_results": {"zh": "结果", "en": "Results"},
    # ---- key panel ----------------------------------------------------
    "key_source_label": {
        "zh": "从游戏文件识别：System.json、rpg_core.js 或任意加密图片",
        "en": "Detect from a game file: System.json, rpg_core.js or any encrypted image",
    },
    "browse_key_file": {"zh": "选择文件…", "en": "Choose file…"},
    "detect_key": {"zh": "识别密钥", "en": "Detect key"},
    "key_label": {"zh": "密钥（十六进制）", "en": "Key (hex)"},
    "key_placeholder": {
        "zh": "例如 1234567890abcdef1234567890abcdef",
        "en": "e.g. 1234567890abcdef1234567890abcdef",
    },
    "key_hint": {
        "zh": "加解密必填；还原图片不需要密钥。",
        "en": "Required for en-/decrypt; restoring images needs no key.",
    },
    "copy_key": {"zh": "复制", "en": "Copy"},
    "paste_key": {"zh": "粘贴", "en": "Paste"},
    "clear_key": {"zh": "清空", "en": "Clear"},
    "key_detected": {"zh": "已识别到密钥", "en": "Key detected"},
    "key_not_found": {"zh": "没有找到密钥", "en": "No key found"},
    "key_detect_hint": {
        "zh": "密钥通常在 www/data/System.json（MZ 为 data/System.json）里，"
        "也可以直接从加密图片推出。",
        "en": "The key usually lives in www/data/System.json (MZ: data/System.json), "
        "or can be recovered from an encrypted image.",
    },
    "key_unverified": {
        "zh": "注意：该文件的头参数无法校验，这个密钥未经确认，请先试解一张图片。",
        "en": "Note: the header values could not be verified, so this key is "
        "unconfirmed - decrypt one image to check it.",
    },
    # ---- files panel --------------------------------------------------
    "add_files": {"zh": "添加文件…", "en": "Add files…"},
    "add_folder": {"zh": "添加文件夹…", "en": "Add folder…"},
    "remove_selected": {"zh": "移除选中", "en": "Remove selected"},
    "clear_list": {"zh": "清空列表", "en": "Clear list"},
    "drag_hint": {
        "zh": "也可以把文件或文件夹直接拖进来",
        "en": "You can also drag files or folders in here",
    },
    "column_file": {"zh": "文件", "en": "File"},
    "column_type": {"zh": "类型", "en": "Type"},
    "column_size": {"zh": "大小", "en": "Size"},
    "column_status": {"zh": "状态", "en": "Status"},
    "count_selected": {"zh": "已选 {count} 个文件", "en": "{count} file(s) selected"},
    "count_mixed": {
        "zh": "已选 {count} 个文件（其中 {usable} 个可用于当前操作）",
        "en": "{count} file(s) selected ({usable} usable for this operation)",
    },
    # ---- options ------------------------------------------------------
    "options": {"zh": "高级设置", "en": "Advanced"},
    "verify_header": {"zh": "校验伪头", "en": "Verify fake header"},
    "verify_header_hint": {"zh": "文件头不匹配时取消勾选。", "en": "Untick if the header does not match."},
    "header_len": {"zh": "头长度", "en": "Header length"},
    "signature": {"zh": "Signature", "en": "Signature"},
    "version_field": {"zh": "Version", "en": "Version"},
    "remain": {"zh": "Remain", "en": "Remain"},
    "reset_defaults": {"zh": "恢复默认", "en": "Reset to defaults"},
    "recursive": {"zh": "递归处理子文件夹", "en": "Include sub-folders"},
    "package_zip": {"zh": "额外打包成 ZIP", "en": "Also create a ZIP"},
    "package_zip_hint": {"zh": "可选，默认只导出文件夹。", "en": "Optional; the folder alone is usually easier to browse."},
    # ---- actions ------------------------------------------------------
    "run_decrypt": {"zh": "解密", "en": "Decrypt"},
    "run_encrypt_mv": {"zh": "加密为 MV", "en": "Encrypt for MV"},
    "run_encrypt_mz": {"zh": "加密为 MZ", "en": "Encrypt for MZ"},
    "run_restore": {"zh": "还原 PNG 头", "en": "Restore PNG headers"},
    "cancel": {"zh": "取消", "en": "Cancel"},
    "copy_report": {"zh": "复制报告", "en": "Copy report"},
    # ---- progress -----------------------------------------------------
    "idle": {"zh": "就绪", "en": "Ready"},
    "scanning": {
        "zh": "正在读取文件列表…已找到 {count} 个",
        "en": "Scanning… {count} file(s) found so far",
    },
    "working": {"zh": "正在处理 {done}/{total}：{name}", "en": "Processing {done}/{total}: {name}"},
    "finished_ok": {
        "zh": "完成：{ok} 个成功，{skipped} 个跳过，{failed} 个失败",
        "en": "Done: {ok} succeeded, {skipped} skipped, {failed} failed",
    },
    "finished_with_errors": {
        "zh": "完成（有失败项）：{ok} 个成功，{skipped} 个跳过，{failed} 个失败",
        "en": "Finished with failures: {ok} succeeded, {skipped} skipped, {failed} failed",
    },
    "cancelled": {"zh": "已取消", "en": "Cancelled"},
    "exported_to": {"zh": "已导出到 {path}", "en": "Exported to {path}"},
    "not_started": {"zh": "未开始：{error}", "en": "Not started: {error}"},
    "failed": {"zh": "失败：{error}", "en": "Failed: {error}"},
    "nothing_to_do": {"zh": "没有可处理的文件", "en": "Nothing to process"},
    "nothing_to_process_hint": {
        "zh": "选中的文件里没有本操作支持的扩展名（需要 {extensions}）",
        "en": "None of the selected files has an extension this operation handles "
        "(needs {extensions})",
    },
    "all_already_done": {
        "zh": "选中的文件都已转换过，无需重复处理",
        "en": "Every selected file was already converted",
    },
    # ---- status text --------------------------------------------------
    "status_ok": {"zh": "成功", "en": "OK"},
    "status_failed": {"zh": "失败", "en": "Failed"},
    "status_skipped": {"zh": "跳过", "en": "Skipped"},
    "status_pending": {"zh": "待处理", "en": "Pending"},
    "status_unusable": {"zh": "不适用", "en": "Not usable"},
    # ---- dialogs ------------------------------------------------------
    "choose_key_file": {
        "zh": "选择用于识别密钥的文件",
        "en": "Choose a file to detect the key from",
    },
    "choose_inputs": {"zh": "选择要处理的文件", "en": "Choose files to process"},
    "choose_folder": {"zh": "选择文件夹", "en": "Choose a folder"},
    "choose_output": {"zh": "选择导出根目录", "en": "Choose the export root"},
    "output_root_label": {"zh": "导出根目录", "en": "Export root"},
    "change_output": {"zh": "更改…", "en": "Change…"},
    "output_hint": {
        "zh": "每次运行会在这里新建一个时间戳文件夹，不会覆盖已有文件。",
        "en": "Each run creates a new timestamped folder here; nothing is overwritten.",
    },
    "output_folder_unavailable": {
        "zh": "导出目录无法使用：{error}",
        "en": "The export folder is unusable: {error}",
    },
    "browse_results": {
        "zh": "查看导出结果",
        "en": "View results",
    },
    "browse_results_tip": {
        "zh": "在窗口内查看导出目录的内容——不依赖系统文件管理器。",
        "en": "Show the export folder's contents inside this window; no file manager needed.",
    },
    "browse_summary": {
        "zh": "{folders} 个文件夹，{files} 个文件，共 {size}",
        "en": "{folders} folders, {files} files, {size} in total",
    },
    "browse_folder_row": {"zh": "文件夹", "en": "folder"},
    "browse_column_name": {"zh": "名称", "en": "Name"},
    "browse_column_type": {"zh": "类型", "en": "Type"},
    "browse_column_size": {"zh": "大小", "en": "Size"},
    "browse_up": {"zh": "上级目录", "en": "Up"},
    "browse_copy_path": {"zh": "复制路径", "en": "Copy path"},
    "browse_preview": {"zh": "预览", "en": "Preview"},
    "browse_pick_a_file": {
        "zh": "选中一个文件即可预览（图片会直接显示）。",
        "en": "Select a file to preview it; images are shown inline.",
    },
    "browse_enter_folder": {
        "zh": "双击进入这个文件夹。",
        "en": "Double-click to open this folder.",
    },
    "browse_no_preview": {
        "zh": "这个类型没有预览。",
        "en": "No preview for this type.",
    },
    "browse_copied": {
        "zh": "已复制：{path}",
        "en": "Copied: {path}",
    },
    "browse_unreadable": {
        "zh": "读不了这个目录：{error}",
        "en": "Cannot read this folder: {error}",
    },
    "output_relocated": {
        "zh": "注意：安装目录不可写，导出改到 {path}",
        "en": "Note: the install folder is not writable, so exports go to {path}",
    },
    "output_is_input_warning": {
        "zh": "你选择的是导出目录（{path}）。如果没有结果，试试选择游戏目录里的资源文件。",
        "en": "You selected an export folder ({path}). If nothing happens, pick the "
        "game's resource files instead.",
    },
    "error_title": {"zh": "出错了", "en": "Error"},
    "files_filter": {
        "zh": "RPG Maker 资源 (*.rpgmvp *.rpgmvm *.rpgmvo *.png_ *.ogg_ *.m4a_ *.png *.ogg *.m4a *.json *.js *.txt);;所有文件 (*)",
        "en": "RPG Maker resources (*.rpgmvp *.rpgmvm *.rpgmvo *.png_ *.ogg_ *.m4a_ *.png *.ogg *.m4a *.json *.js *.txt);;All files (*)",
    },
    "key_filter": {
        "zh": "密钥来源 (*.json *.js *.txt *.rpgmvp *.png_);;所有文件 (*)",
        "en": "Key sources (*.json *.js *.txt *.rpgmvp *.png_);;All files (*)",
    },
    # ---- what each operation means ------------------------------------
    "mode_hint_decrypt": {
        "zh": "把加密资源还原成 .png / .ogg / .m4a",
        "en": "Turn encrypted resources back into .png / .ogg / .m4a",
    },
    "mode_hint_encrypt": {
        "zh": "把改好的 .png / .ogg / .m4a 加密回游戏格式",
        "en": "Encrypt edited .png / .ogg / .m4a back into game format",
    },
    "mode_hint_restore": {
        "zh": "不需要密钥，直接修复加密图片的 PNG 头",
        "en": "Repair encrypted images' PNG headers without a key",
    },
    "hex_hint": {"zh": "以上为十六进制值；一般保持默认即可。", "en": "The values above are hex; the defaults are almost always right."},
    "advanced": {"zh": "高级设置…", "en": "Advanced…"},
    "advanced_title": {"zh": "伪头设置", "en": "Fake header settings"},
    "close": {"zh": "完成", "en": "Done"},
    "report_header": {
        "zh": "RPG Maker MV/MZ 解密工具 – 处理报告",
        "en": "RPG Maker MV/MZ Decrypter - run report",
    },
}


def tr(text_key: str, lang: str = DEFAULT_LANGUAGE, **values: Any) -> Any:
    """Look ``text_key`` up for ``lang`` and format it with ``values``.

    :raises KeyError: for an unknown key, so a typo fails loudly in tests rather
        than showing a raw identifier in the interface
    """
    entry = TEXT[text_key]
    text = entry.get(lang) or entry[DEFAULT_LANGUAGE]
    if not values:
        return text
    return text.format(**values) if isinstance(text, str) else text
