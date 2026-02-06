def explore(path):
    """Explores a directory and returns a JSON object with a tree of all paths, files, and code lines that match a given pattern.

    Args:
        path (str): The path to the directory to explore.

    Returns:
        str: A JSON object representing the tree of paths, files, and code lines.
    """
    import os
    import json

    results = []

    for root, directories, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines):
                        if search_pattern in line:
                            results.append({
                                "path": file_path,
                                "file": file,
                                "line_number": i + 1,
                                "line": line.strip()
                            })
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")

    return json.dumps(results, indent=4)

search_pattern = input("Enter the search pattern: ")