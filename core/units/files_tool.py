import os
import json
import subprocess
import logging
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
from fastapi import FastAPI, HTTPException
from ..framework.base import Unit, UnitResult
from ..utils.llm import make_llm_api_call
from .working_memory import WorkingMemory
from ..utils.file_utils import find_files, EXCLUDED_FILES, EXCLUDED_DIRS, EXCLUDED_EXT, _should_exclude

def _rindex(li, value):
    return len(li) - li[-1::-1].index(value) - 1

@dataclass
class FilesTool(Unit):
    base_path: str = "/Users/markokraemer/Desktop/projects/agent-builder/working_directory"  # Hard coded for now

    def __init__(self):
        """
        Initialize the FilesTool.
        """
        super().__init__()
        self.working_memory = WorkingMemory()
        self.initialize_files()

    def initialize_files(self):
        """
        Initialize the files in the working directory by reading the directory contents.
        """
        if not self.working_memory.get_module("WorkspaceDirectoryContents"):
            self.working_memory.add_or_update_module("WorkspaceDirectoryContents", [])
        self.read_directory_contents("")  # Hardcoded initializes with full latest WorkspaceDirectoryContents

    def _get_effective_path(self, path: str) -> str:
        """
        Get the effective path by handling . and ~ to avoid touching things outside base_path.
        
        :param path: The path to process.
        :return: The effective path.
        """
        # Handling . and ~ to avoid touching things outside base_path.
        path_parts = path.split(os.sep)
        if "." in path_parts:
            remaining_path = path_parts[_rindex(path_parts, ".") + 1 :]
            effective_path = os.path.join(self.base_path, *remaining_path)
        else:
            effective_path = os.path.join(self.base_path, path)
        return effective_path

    def gather_information_ask_user(self, prompt: str) -> UnitResult:
        """
        Request a message from the user.
        
        :param prompt: The prompt to ask the user.
        :return: The user's response.
        """
        self.logger.log(f"Prompting user: {prompt}")
        try:
            user_response = input(prompt)
            return self.success_response(user_response)
        except Exception as e:
            self.logger.log_exception(e)
            return self.fail_response(str(e))

    def edit_mainpy_file_contents(self, instructions: str) -> UnitResult:
        """
        Edit main.py file contents based on instructions.
        
        :param instructions: Instructions on how to edit the file.
        :return: Result of the editing operation.
        """
        self.logger.log(f"Editing main.py with instructions: {instructions}")
        effective_path = self._get_effective_path('main.py')
        if not os.path.exists(effective_path):
            return self.fail_response("File main.py does not exist.")
        try:
            with open(effective_path, 'r') as file:
                current_content = file.read()
            # Construct messages for LLM API call
            messages = [
                {
                    "role": "system",
                    "content": "You are a brilliant and meticulous engineer. When you write code, the code works on the first try, is syntactically perfect and is fully complete. You have the utmost care for the code that you write, so you do not make mistakes and every function and class is fully implemented. \n Under NO CIRCUMSTANCES should the file be stripped of the majority of contents, make deliberate changes instead. \n Make sure to output the complete newFileContents in the JSON property newFileContents, do not create additional properties – but Output the complete File Contents all within 'newFileContents'"
                },
                {"role": "user", "content": f"This is the current content of the file you are editing 'main.py':\n\n<current_content>{current_content}</current_content> \nYou are now implementing the following instructions for main.py: {instructions}\n.\n.Respond in this JSON Format, OUTPUT EVERYTHING IN FOLLOWING JSON PROPERTIES, do not add new properties but output in File, FileName, newFileContents. Make sure to ONLY EDIT main.py. Strictly respond in this JSON Format:\n\n {{\n  \"File\": {{\n    \"FilePath\": \"main.py\",\n    \"newFileContents\": \"The whole file contents, the complete code – The contents of the new file with all instructions implemented perfectly. NEVER write comments. Keep the complete File Contents within this single JSON Property.\"}}\n}}\n"}
            ]
            # Make LLM API call and parse the response
            response = make_llm_api_call(messages, "gpt-4o", json_mode=True, max_tokens=4096) 
            response_content = response.choices[0].message['content']
            response_json = json.loads(response_content)
            new_content = response_json["File"]["newFileContents"]

            # Write the new content into the file
            with open(effective_path, 'w') as file:
                file.write(new_content)
            
            return self.success_response("File 'main.py' edited successfully. Check WorkingMemory for latest contents.")
        except Exception as e:
            self.logger.log_exception(e)
            return self.fail_response(str(e))

    def read_directory_contents(self, path: str, depth: int = 3) -> UnitResult:
        """
        List all files and directories at the given path, including their contents, while excluding certain files and directories as specified in file_utils.py, up to a specified depth. Updates the WorkspaceDirectoryContents Module in working memory with the directory contents.
        """
        self.logger.log(f"Reading directory contents for path: {path} up to depth: {depth}")
        if not os.path.exists(self.base_path):
            return self.fail_response("Base path does not exist")
        effective_path = self._get_effective_path(path)
        if not os.path.exists(effective_path) or not os.path.isdir(effective_path):
            return self.fail_response("Directory does not exist or is not a directory")

        try:
            directory_contents = {}
            for root, dirs, files in os.walk(effective_path):
                # Calculate current depth
                current_depth = os.path.relpath(root, effective_path).count(os.sep)
                if current_depth > depth:
                    dirs[:] = []  # Don't go any deeper
                else:
                    # Apply exclusions for directories
                    dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not _should_exclude(self.base_path, os.path.join(root, d))]
                    # Apply exclusions for files
                    files = [f for f in files if f not in EXCLUDED_FILES and not any(f.endswith(ext) for ext in EXCLUDED_EXT) and not _should_exclude(self.base_path, os.path.join(root, f))]
                    # Append relative paths of files and directories to contents and read file contents
                    for file in files:
                        file_path = os.path.join(root, file)
                        relative_file_path = os.path.relpath(file_path, effective_path)
                        if not _should_exclude(self.base_path, file_path):
                            try:
                                with open(file_path, 'r', encoding='utf-8') as file_content:
                                    directory_contents[relative_file_path] = file_content.read()
                            except UnicodeDecodeError:
                                # Skip files that cannot be decoded with UTF-8
                                continue
            # Update the WorkspaceDirectoryContents Module in working memory
            self.working_memory.add_or_update_module("WorkspaceDirectoryContents", directory_contents)
            return self.success_response({"contents": directory_contents})
        except Exception as e:
            self.logger.log_exception(e)
            return self.fail_response(str(e))

    @staticmethod
    def schema() -> List[Dict[str, Any]]:
        """
        Returns the OpenAPI JSON schema for function calls in the Agent Tool.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": FilesTool.gather_information_ask_user.__name__,
                    "description": FilesTool.gather_information_ask_user.__doc__,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "The prompt to ask the user.",
                            }
                        },
                        "required": ["prompt"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": FilesTool.edit_mainpy_file_contents.__name__,
                    "description": FilesTool.edit_mainpy_file_contents.__doc__,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "instructions": {
                                "type": "string",
                                "description": "Instructions on how to edit the main.py file.",
                            }
                        },
                        "required": ["instructions"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": FilesTool.read_directory_contents.__name__,
                    "description": FilesTool.read_directory_contents.__doc__,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The directory path to read contents from.",
                            },
                            "depth": {
                                "type": "integer",
                                "description": "The depth to which the directory contents should be read.",
                                "default": 3,
                            }
                        },
                        "required": ["path"],
                    },
                },
            }, 
        ]

if __name__ == "__main__":
    files_tool_instance = FilesTool()

    # Example usage of gathering information from the user
    user_prompt = "Please provide your input: "
    gather_info_result = files_tool_instance.gather_information_ask_user(user_prompt)
    print(f"User input: {gather_info_result.output}")
    input("Press ENTER to continue...")

    # Example usage of editing main.py file contents
    edit_instructions = "Add a function to return the sum of two numbers."
    edit_file_result = files_tool_instance.edit_mainpy_file_contents(edit_instructions)
    print(f"Editing main.py with instructions '{edit_instructions}': {edit_file_result.output}")
    input("Press ENTER to continue...")
