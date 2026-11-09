import configparser
import json
import os
import mimetypes
import shutil
import time

from openai import OpenAI


def typewriter_print(text, delay=0.03):
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()


def load_config():
    config = configparser.ConfigParser()
    config.read("config.ini", encoding="utf-8")
    llm = config["llm"]
    return llm["base_url"], llm["api_key"], llm["model"]


def isLeapYear(year):
    try:
        y = int(year)
        if (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0):
            return f"{y} 年是闰年。"
        else:
            return f"{y} 年不是闰年。"
    except (ValueError, TypeError):
        return "请输入有效的年份（整数）。"
def get_current_working_directory():
    try:
        cwd = os.getcwd()
        return f"当前工作目录：{cwd}"
    except Exception as e:
        return f"获取当前工作目录失败：{e}"


def list_files_in_directory(directory="."):
    try:
        path = directory if directory else "."
        if not os.path.exists(path):
            return f"目录不存在：{path}"
        if not os.path.isdir(path):
            return f"指定路径不是目录：{path}"
        entries = os.listdir(path)
        files = []
        dirs = []
        for entry in sorted(entries):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                dirs.append(f"[DIR] {entry}")
            else:
                files.append(f"[FILE] {entry}")
        result = dirs + files
        if not result:
            return f"目录 {path} 为空。"
        return "\n".join(result)
    except Exception as e:
        return f"列出目录文件失败：{e}"


def get_file_type(file_path):
    try:
        if not os.path.exists(file_path):
            return f"文件不存在：{file_path}"
        if os.path.isdir(file_path):
            return f"指定路径是目录，不是文件：{file_path}"
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            return f"文件：{file_path}\n文件类型（MIME）：{mime_type}"
        ext = os.path.splitext(file_path)[1]
        if ext:
            return f"文件：{file_path}\n文件扩展名：{ext}\n无法推断 MIME 类型。"
        return f"文件：{file_path}\n无扩展名，无法推断文件类型。"
    except Exception as e:
        return f"获取文件类型失败：{e}"


def is_text_file(file_path):
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
        if b"\x00" in chunk:
            return False
        return True
    except Exception:
        return False


def get_file_content(file_path):
    try:
        if not os.path.exists(file_path):
            return f"文件不存在：{file_path}"
        if os.path.isdir(file_path):
            return f"指定路径是目录，不是文件：{file_path}"
        if not is_text_file(file_path):
            return f"不支持读取非纯文本文件：{file_path}"
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 10000:
            return content[:10000] + "\n\n[内容过长，已截断前 10000 字符]"
        return content
    except Exception as e:
        return f"获取文件内容失败：{e}"


def create_file(directory, file_name):
    try:
        dir_path = directory if directory else "."
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        if not os.path.isdir(dir_path):
            return f"指定路径不是目录：{dir_path}"
        file_path = os.path.join(dir_path, file_name)
        if os.path.exists(file_path):
            return f"文件已存在：{file_path}"
        with open(file_path, "w", encoding="utf-8") as f:
            pass
        return f"文件创建成功：{file_path}"
    except Exception as e:
        return f"创建文件失败：{e}"


def edit_file_content(file_path, content):
    try:
        if not os.path.exists(file_path):
            return f"文件不存在：{file_path}"
        if os.path.isdir(file_path):
            return f"指定路径是目录，不是文件：{file_path}"
        if not is_text_file(file_path):
            return f"不支持编辑非纯文本文件：{file_path}"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"文件编辑成功：{file_path}"
    except Exception as e:
        return f"编辑文件失败：{e}"


def create_directory(directory_path):
    try:
        if not directory_path:
            return "请提供目录路径。"
        if os.path.exists(directory_path):
            if os.path.isdir(directory_path):
                return f"目录已存在：{directory_path}"
            else:
                return f"指定路径已存在且不是目录：{directory_path}"
        os.makedirs(directory_path, exist_ok=True)
        return f"目录创建成功：{directory_path}"
    except Exception as e:
        return f"创建目录失败：{e}"


def delete_directory(directory_path):
    try:
        if not directory_path:
            return "请提供目录路径。"
        if not os.path.exists(directory_path):
            return f"目录不存在：{directory_path}"
        if not os.path.isdir(directory_path):
            return f"指定路径不是目录：{directory_path}"
        shutil.rmtree(directory_path)
        return f"目录删除成功（非空目录已删除）：{directory_path}"
    except Exception as e:
        return f"删除目录失败：{e}"


def delete_file(file_path):
    try:
        if not file_path:
            return "请提供文件路径。"
        if not os.path.exists(file_path):
            return f"文件不存在：{file_path}"
        if os.path.isdir(file_path):
            return f"指定路径是目录，请使用删除目录功能：{file_path}"
        os.remove(file_path)
        return f"文件删除成功：{file_path}"
    except Exception as e:
        return f"删除文件失败：{e}"

def main():
    base_url, api_key, model = load_config()
    client = OpenAI(base_url=base_url, api_key=api_key)

    history = []

    tools = [
        {
            "type": "function",
            "function": {
                "name": "isLeapYear",
                "description": "计算输入的年份是否是闰年。使用 Python 代码计算闰年规则（能被 4 整除且不能被 100 整除，或能被 400 整除）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "year": {
                            "type": "integer",
                            "description": "要判断的年份，如 2024、2000、1900",
                        }
                    },
                    "required": ["year"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_current_working_directory",
                "description": "获取当前工作目录。",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files_in_directory",
                "description": "列出指定目录下所有文件和子目录。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "指定目录路径，默认为当前目录（.）。"},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_file_type",
                "description": "获取指定文件的文件类型（MIME 类型或扩展名）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径。"},
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_file_content",
                "description": "获取指定文件的内容（仅支持纯文本格式文件）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径。"},
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_file",
                "description": "根据指定的目录和文件名创建新文件（如果目录不存在会自动创建）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "目标目录路径，默认为当前目录（.）。"},
                        "file_name": {"type": "string", "description": "要创建的文件名。"},
                    },
                    "required": ["file_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit_file_content",
                "description": "编辑指定文件的内容（仅支持纯文本格式文件，会覆盖原内容）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径。"},
                        "content": {"type": "string", "description": "新的文件内容。"},
                    },
                    "required": ["file_path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_directory",
                "description": "创建新目录（如果目录已存在会提示，如果路径已存在但不是目录也会提示，支持嵌套目录创建）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory_path": {"type": "string", "description": "要创建的目录路径。"},
                    },
                    "required": ["directory_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_directory",
                "description": "删除目录（非空目录也会被删除）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory_path": {"type": "string", "description": "要删除的目录路径。"},
                    },
                    "required": ["directory_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_file",
                "description": "删除文件。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "要删除的文件路径。"},
                    },
                    "required": ["file_path"],
                },
            },
        },
    ]

    while True:
        try:
            user_input = input("请输入消息：").strip()
        except EOFError:
            break
        if user_input.lower() in ("exit", "quit", "q"):
            break

        history.append({"role": "user", "content": user_input})

        response = client.chat.completions.create(
            model=model,
            messages=history,
            tools=tools,
            tool_choice="auto",
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls

        if tool_calls:
            history.append(message)

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = tool_call.function.arguments
                try:
                    args = json.loads(function_args) if function_args else {}
                except Exception:
                    args = {}

                tool_result = "未知工具调用"
                if function_name == "isLeapYear":
                    year = args.get("year")
                    tool_result = isLeapYear(year)
                elif function_name == "get_current_working_directory":
                    tool_result = get_current_working_directory()
                elif function_name == "list_files_in_directory":
                    tool_result = list_files_in_directory(args.get("directory"))
                elif function_name == "get_file_type":
                    tool_result = get_file_type(args.get("file_path"))
                elif function_name == "get_file_content":
                    tool_result = get_file_content(args.get("file_path"))
                elif function_name == "create_file":
                    tool_result = create_file(args.get("directory"), args.get("file_name"))
                elif function_name == "edit_file_content":
                    tool_result = edit_file_content(args.get("file_path"), args.get("content"))
                elif function_name == "create_directory":
                    tool_result = create_directory(args.get("directory_path"))
                elif function_name == "delete_directory":
                    tool_result = delete_directory(args.get("directory_path"))
                elif function_name == "delete_file":
                    tool_result = delete_file(args.get("file_path"))

                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )

            response = client.chat.completions.create(
                model=model,
                messages=history,
            )
            reply = response.choices[0].message.content
        else:
            reply = message.content

        print("-" * 40)
        if reply:
            typewriter_print(reply)
        else:
            print("(无回复)")

        if not tool_calls and reply:
            history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
