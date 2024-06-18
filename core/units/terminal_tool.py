import subprocess
import os
import tempfile
import json
import time
import re
from ..framework.base import Unit, UnitResult
from ..utils.workspace_utils import get_docker_container_id
from .working_memory import WorkingMemory
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class TerminalTool(Unit):
    logs_dir: str = "/Users/markokraemer/Desktop/projects/agent-builder/working_directory/terminal_logs"


    def __init__(self):
        """
        Initializes the TerminalTool instance by setting up a temporary directory for logs,
        retrieving the container ID, and initializing terminal sessions.
        """
        super().__init__()
        os.makedirs(self.logs_dir, exist_ok=True)
        container_id = get_docker_container_id("workspace_dev-env_1")
        if container_id is None:
            raise ValueError("No running container found for the standard docker image.")
        self.container_name = container_id
        self.working_memory = WorkingMemory()
        self.initialize_terminal_sessions()

    def initialize_terminal_sessions(self):
        """
        Initializes the TerminalSessions module with an empty list if it doesn't already exist.
        """
        if not self.working_memory.get_module("TerminalSessions"):
            self.working_memory.add_or_update_module("TerminalSessions", [])

    def new_terminal_session(self) -> str:
        """
        Creates a new terminal session and returns its session ID.
        """
        self.logger.log("Creating a new terminal session.")
        terminal_sessions = self.working_memory.get_module("TerminalSessions")
        session_id = f"session_{len(terminal_sessions) + 1}"
        log_file_path = os.path.join(self.logs_dir, f"{session_id}.log")
        kill_command = f"tmux kill-session -t {session_id}"
        subprocess.run(kill_command, shell=True)  # Ignore errors if session does not exist

        try:
            command = f"tmux new-session -d -s {session_id} 'docker exec -it {self.container_name} /bin/bash | ts \"%Y-%m-%d-%H:%M:%S\" > {log_file_path}'"
            subprocess.run(command, shell=True, check=True)
            terminal_sessions.append({"session_id": session_id, "action_history": []})
            self.working_memory.add_or_update_module("TerminalSessions", terminal_sessions)
            self.logger.log(f"New terminal session created with ID: {session_id}")
        except subprocess.CalledProcessError as e:
            self.logger.log_exception(e)
            raise RuntimeError(f"Failed to create new tmux session for {session_id}")
        return session_id

    def control_c_terminal_session(self, session_id: str) -> UnitResult:
        """
        Closes the specified terminal session and returns a UnitResult indicating success or failure.
        """
        self.logger.log(f"Closing terminal session with ID: {session_id}")
        try:
            command = f"tmux kill-session -t {session_id}"
            subprocess.run(command, shell=True, check=True)
            terminal_sessions = self.working_memory.get_module("TerminalSessions")
            closed_session = [session for session in terminal_sessions if session["session_id"] == session_id]
            terminal_sessions = [session for session in terminal_sessions if session["session_id"] != session_id]
            self.working_memory.add_or_update_module("TerminalSessions", terminal_sessions)
            if closed_session:
                return self.success_response(f"CLOSED session_id: {closed_session[0]}")
            else:
                return self.fail_response("Session ID not found")
        except subprocess.CalledProcessError as e:
            self.logger.log_exception(e)
            return self.fail_response(f"Failed to kill tmux session {session_id}")

    def send_terminal_command(self, session_id: str, command: str) -> UnitResult:
        """
        Sends a command to the specified terminal session and updates the session's action and history.
        """
        self.logger.log(f"Sending command to terminal session {session_id}: {command}")
        tmux_command = f"tmux send-keys -t {session_id} '{command}' Enter"
        try:
            subprocess.run(tmux_command, shell=True, check=True)
            self.update_action_history(session_id, command)
            self.observe_terminal_session(session_id, 0, 0)  # Update the session history immediately
            return self.success_response("Command executed")
        except subprocess.CalledProcessError as e:
            self.logger.log_exception(e)
            return self.fail_response("Failed to send command to tmux session")

    def observe_terminal_session(self, session_id: str, offset_start_time_by_in_seconds: int, observation_time_in_seconds: int) -> str:
        """
        Observes the terminal session for a specified duration and returns the logs.
        """
        self.logger.log(f"Observing terminal session {session_id} from {offset_start_time_by_in_seconds} seconds ago for {observation_time_in_seconds} seconds.")
        terminal_sessions = self.working_memory.get_module("TerminalSessions")
        for session in terminal_sessions:
            if session["session_id"] == session_id:
                log_file_path = os.path.join(self.logs_dir, f"{session_id}.log")
                start_time = time.time()
                actual_start_time = start_time - offset_start_time_by_in_seconds
                end_time = start_time + observation_time_in_seconds
                time.sleep(observation_time_in_seconds)
                observed_logs = []

                try:
                    with open(log_file_path, 'r') as log_file:
                        log_content = log_file.read()
                        log_lines = log_content.split('\n')
                        within_time_range = False
                        for line in log_lines:
                            match = re.match(r'(\d{4}-\d{2}-\d{2}-\d{2}:\d{2}:\d{2})', line)
                            if match:
                                log_time = time.mktime(time.strptime(match.group(1), "%Y-%m-%d-%H:%M:%S"))
                                within_time_range = actual_start_time <= log_time <= end_time
                                if within_time_range:
                                    observed_logs.append(line)
                            elif within_time_range:
                                observed_logs.append(line)
                except FileNotFoundError:
                    return "Log file not found. It's possible the session has not generated any output yet."

                return "\n".join(observed_logs)
        return "Session not found or no history available."

    def update_action_history(self, session_id: str, command: str):
        """Updates the action history of a terminal session with the command sent."""
        self.logger.log(f"Updating action history for session {session_id} with command: {command}")
        terminal_sessions = self.working_memory.get_module("TerminalSessions")
        timestamp = time.strftime("%Y-%m-%d-%H:%M:%S", time.localtime())
        for session in terminal_sessions:
            if session["session_id"] == session_id:
                session["action_history"].append(f"{timestamp} - {command}")
                self.working_memory.add_or_update_module("TerminalSessions", terminal_sessions)
                break

    @staticmethod
    def schema() -> List[Dict[str, Any]]:
        """
        Returns the OpenAPI JSON schema for function calls.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": TerminalTool.new_terminal_session.__name__,
                    "description": TerminalTool.new_terminal_session.__doc__,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": TerminalTool.control_c_terminal_session.__name__,
                    "description": TerminalTool.control_c_terminal_session.__doc__,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "The session ID of the terminal session to close.",
                            }
                        },
                        "required": ["session_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": TerminalTool.send_terminal_command.__name__,
                    "description": TerminalTool.send_terminal_command.__doc__,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "The session ID to which the command will be sent.",
                            },
                            "command": {
                                "type": "string",
                                "description": "The command to be executed in the terminal session.",
                            }
                        },
                        "required": ["session_id", "command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": TerminalTool.observe_terminal_session.__name__,
                    "description": TerminalTool.observe_terminal_session.__doc__,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "The session ID of the terminal session to observe.",
                            },
                            "offset_start_time_by_in_seconds": {
                                "type": "integer",
                                "description": "The number of seconds to offset the start time of the observation output.",
                                "default": 5
                            },
                            "observation_time_in_seconds": {
                                "type": "integer",
                                "description": "The duration in seconds for which the terminal session will be observed.",
                            }
                        },
                        "required": ["session_id", "offset_start_time_by_in_seconds", "observation_time_in_seconds"],
                    },
                },
            },
        ]

if __name__ == "__main__":
    terminal_tool_instance = TerminalTool()

    # Step 1: Generate a terminal session
    session_id = terminal_tool_instance.new_terminal_session()
    print(f"Generated terminal session ID: {session_id}")

    # Step 2: Dispatch a command to the terminal session
    command = "echo 'Hello, World!'"
    execution_result = terminal_tool_instance.send_terminal_command(session_id, command)
    print(f"Dispatched command to session: {command}\nExecution Result: {execution_result.output}")

    # Step 3: Observe the terminal session for the command output
    observed_logs = terminal_tool_instance.observe_terminal_session(session_id, 20, 2)
    print(f"Observed logs for session {session_id}:\n{observed_logs}")

    # # Step 4: Dispatch another command to the same terminal session
    # another_command = "ls -la"
    # another_execution_result = terminal_tool_instance.send_terminal_command(session_id, another_command)
    # print(f"Dispatched another command to session: {another_command}\nExecution Result: {another_execution_result.output}")

    # # Step 5: Observe the terminal session again for the new command output
    # observed_logs_again = terminal_tool_instance.observe_terminal_session(session_id, 0, 5)
    # print(f"Observed logs for session {session_id} after second command:\n{observed_logs_again}")

    # # Step 6: Terminate the terminal session
    # termination_result = terminal_tool_instance.control_c_terminal_session(session_id)
    # print(f"Terminal session with ID {session_id} has been terminated. Result: {termination_result.output}")
