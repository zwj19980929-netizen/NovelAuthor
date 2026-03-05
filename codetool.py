import os

def get_file_contents(directory, extensions, ignore_files=None, ignore_dirs=None):
    """
    获取指定目录下符合特定扩展名且不在忽略列表中的文件内容，
    同时跳过指定的忽略目录及其所有子内容。

    Args:
        directory (str): 要遍历的目录路径。
        extensions (tuple or str): 允许的文件扩展名（例如 '.py' 或 ('.py', '.txt')）。
        ignore_files (list or tuple, optional): 要忽略的文件名列表。默认为 None。
        ignore_dirs (list or tuple, optional): 要忽略的目录名列表。默认为 None。

    Returns:
        list: 包含每个文件相对路径和内容的字符串列表。
    """
    contents = []
    # 初始化忽略集合
    ignored_files_set = set(ignore_files) if ignore_files else set()
    ignored_dirs_set = set(ignore_dirs) if ignore_dirs else set()

    # os.walk 默认 topdown=True，允许我们在遍历时修改 dirs 列表
    for root, dirs, files in os.walk(directory, topdown=True):
        # --- 核心改动：过滤掉要忽略的目录 ---
        # dirs[:] = [...] 会原地修改 dirs 列表，
        # os.walk 在接下来的迭代中将不会进入被移除的目录
        dirs[:] = [d for d in dirs if d not in ignored_dirs_set]

        # --- 文件处理逻辑（与之前类似）---
        for file in files:
            # 检查文件扩展名
            if file.endswith(extensions):
                # 检查文件名是否包含 "codetool"
                # 检查文件名是否在忽略文件列表中
                if "codetool" not in file and file not in ignored_files_set:
                    full_path = os.path.join(root, file)
                    # 计算相对路径，保持相对于初始的 directory
                    relative_path = os.path.relpath(full_path, start=directory)
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            contents.append(f"{relative_path}:\n{f.read()}\n")
                    except UnicodeDecodeError:
                        print(f"Warning: Could not decode file {full_path} with UTF-8. Skipping.")
                    except IOError as e:
                        print(f"Warning: Could not read file {full_path}. Error: {e}. Skipping.")
    return contents

def write_to_file(contents, output_file):
    """将内容列表写入指定文件。"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.writelines(contents)
        print(f"Successfully wrote contents to {output_file}")
    except IOError as e:
        print(f"Error: Could not write to file {output_file}. Error: {e}")

if __name__ == "__main__":
    directory = r'TrinityAI' # 目标根目录
    # directory = './lmtester/.venv/Lib/site-packages/mcp'
    extensions = ('.py','.js','.css', '.html','.yaml',".config.js",".vue")   # 要包含的文件扩展名

    # --- 在这里定义你想要忽略的文件名列表 ---
    # 只需写文件名，不需要路径
    files_to_ignore = ['']

    # --- 在这里定义你想要忽略的目录名列表 ---
    # 只需写目录名，不需要路径。os.walk 会跳过这些目录及其所有子内容
    # 例如： 'venv', '.git', '__pycache__', 'build', 'dist', 'docs'
    dirs_to_ignore = ['.venv'] # 示例列表，请根据需要修改
    # dirs_to_ignore = []

    output_file = 'result.txt'

    # 调用 get_file_contents 时传入要忽略的文件和目录列表
    file_contents = get_file_contents(
        directory,
        extensions,
        ignore_files=files_to_ignore,
        ignore_dirs=dirs_to_ignore
    )

    if file_contents:
        write_to_file(file_contents, output_file)
    else:
        print("No files found matching the criteria or all matching files/directories were ignored.")