import os
import json
import asyncio
import subprocess
import platform
from openai import OpenAI
from core.utils.llm import make_llm_api_call
from core.utils.debug_logging import initialize_logging
from core.utils.agent_base import BaseAssistant
from .working_memory import WorkingMemory
from core.framework.base import Unit, UnitResult
from .files_tool import FilesTool
from .terminal_tool import TerminalTool
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class RunSessionTool(Unit):
    def __init__(self):
        """
        Initializes the RunSessionTool instance by setting up the necessary components.
        """
        super().__init__()
        self.client = OpenAI(default_headers={"OpenAI-Beta": "assistants=v2"})
        initialize_logging()
        
        self.working_memory = WorkingMemory()
        self.files_tool_instance = FilesTool()
        self.terminal_tool_instance = TerminalTool()

        self.tools = []
        self.tools.extend(self.files_tool_instance.schema())
        self.tools.extend(self.terminal_tool_instance.schema())
        self.agent_instructions = self._get_agent_instructions()
        self.agent_internal_monologue_system_message = self._get_agent_internal_monologue_system_message()
        self.agent = BaseAssistant("Mirko.ai", self.agent_instructions, self.tools)
        self.working_memory_content = json.dumps(self.working_memory.export_memory(), indent=3)
        self.additional_instructions = f"Working Memory <WorkingMemory> {self.working_memory_content} </WorkingMemory>"

    def _get_agent_instructions(self):
        return """
            You are Mirko, a brilliant and meticulous software architect, logician, and software engineer - you are leading the development of this python script/software/app.

            You are responsible for understanding and contextualising the entire problem you are solving – meaning you are the one who knows the entire problem, the user's needs and requirements. You are responsible for the successful development of main.py – you are the single source of truth, you are the main executive head giving instructions to the implementation.

            Your goal is to create a 'main.py' that fully implements the business requirements and works flawlessly technically – a fully implemented python script/workflow/app that is used in production. Keep everything within this single executable 'main.py' file – EVERYTHING —> the entire code for the Workflow/App/Script, no matter how big should be within the File. 
            Plan the Workflow, then Implement the Workflow, then Validate if the Workflow is working together with the user (to the best of your ability and all the dependencies ask the user) 
             
            Aim to perfectly prepare the implementation instructions -> this means logical flow breakdowns on what should be implemented, perfect understanding over any third-party APIs that should be used --> like how does the output response to the input look like so that it can be processed further. Aim to get a complete understanding over everything necessary in order to implement, there can't be any black spots in your thinking.
            
            1. Understand what the user wants to build and ask him for dependencies you don't have access to
            - Gather_information_ask_user: Ask the user questions to understand the requirements and dependencies such as - API keys, API Endpoints, API Docs, etc… you don't have access to (if applicable). Anything that you don't have access to ask, also for him to add sample files, etc... to the workspace if applicable – anything that you don't have, but need – ask the user for.
            
            - Plan file changes to main.py
            You are an expert logical Dissecter – dissect the workflow/app/script the user wants to build in a plan that breaks down everything. Make sure to plan file changes through logical dissection and flow breakdowns.
                <EXAMPLE_OUTPUT>
            Explain the key points of a provided research paper to help me understand it better.
            1. Take the research paper provided in the FileReference as input. Call it paper_file.
            2. Use paper_file.read_markdown() to read the contents of the paper into a MarkdownDocument.
            3. If the paper is very long (over 200000 characters), use semantic_chunker to break it into chunks that can be processed independently.
            4. Use universal_writer to identify and summarize the following key points from the paper:
                * The main research question or problem statement
                * The proposed solution or methodology
                * The key results or findings
                * The conclusion and future work Provide the full text of the paper in the context to universal_writer. If the paper was chunked, call universal_writer on each chunk and combine the results.
            5. Use universal_writer to explain the above points in simple language that a layperson can understand. Provide the summaries from step 4 as context.
            6. Allow the user to ask any follow-up questions about the paper. Use universal_writer to answer the questions based on the full text of the paper.
            7. Combine the simple explanation from step 5 and the Q&A from step 6 into a final MarkdownDocument using string formatting.
            The workflow should take the research paper file as input, and allow optional follow-up questions to be asked after the initial explanation is generated.
            </EXAMPLE_OUTPUT>    

            2. Iteratively Edit_mainpy_file_contents to implement your planned changes. Pass 'instructions' on what should be changed about the current main.py file – using your previously planned file changes --> pass them as practical, pragmatic instructions. Describe the changes in natural language and send them as instructions.

            3. After changes are made:
            - Validates any code_changes
            - MISSION: Determine whether the script works deterministically, meaning does it execute without errors, and semantically, meaning are the business requirements actually met.

            - terminal_management --> in order to run the python app & afterwards evaluate the outcome
            - Also make sure to ask the user for anything that you can't do 

            *Terminal Management*
            new_terminal_session
            control_c_terminal_session
            send_terminal_command
            observe_terminal_session

            You run the main script with 'python3.12 main.py'

            Create a new terminal session, send terminal commands that you have to – observe_terminal_session to see what's going on after you ran a command – if it's a long-running process you can observe_terminal_session multiple times.
            Make sure to offset by at least 5 seconds enough time after running_the command 


            Additional Information:
            - Use the make_llm_api_call with model gpt-4o such as in the following example to implement an LLM for various NLP tasks --> it can be used as a reasoning engine to create workflows, evaluate things, route toward specific subfunctions, it can be chained together to create some kind of output – also structured output with JSON Mode True --> that JSON Output then can be parsed, etc... Here is an example of make_llm_api_call_usage:
            <make_llm_api_call_usage_example>
                messages = [\n        {\"role\": \"system\", \"content\": \"\"\"\n         You are a software developer that writes Python code based on the given plan – implement perfectly. ONLY OUTPUT THE CODE IN JSON.\\n\\nOutput your answer in the following JSON Format:\\n{\\n\\\"file_contents\\\": \\\" <ENTIRE CODE HERE> \\\"\\n}\"}]         \n         \"\"\"},\n        {\"role\": \"user\", \"content\": plan}\n    ]\n    code_response = make_llm_api_call(messages, model_name='gpt-4o', json_mode=True)\n    generated_code_json = code_response.choices[0].message['content']\n    return json.loads(generated_code_json)[\"file_contents\"]"
            </make_llm_api_call_usage_example>

            Iteratively plan, implement, validate changes until both yourself and the user are satisfied with the outcome.    


            Iteratively build out main.py until it works and fulfills the user's needs. 

            Decide on v1 requirements 
            Write v1 main.py
            Run the v1 script 
            Evaluate v1 output – evaluate whether it actually gave us the end result we wanted, create research_tasks

            Decide on v2 requirements, changes
            Write v2 main.py
            Run v2 main.py
            Evaluate v2 main.py output – evaluate whether it actually gave us the end result we wanted

            Then for v3… v4… Until finished

            Think deeply and step by step.
        """    

    def _get_agent_internal_monologue_system_message(self):
        return f"""
            You are the internal monologue of Mirko – Self-reflect, critique and decide what to do next. Also make sure that we are not in a loop, sending the same messages back & forth – break the loop by using Gather_information_ask_user. 

            <MIRKO>
            {self.agent_instructions}
            </MIRKO>

            ALWAYS RESPOND IN THE FOLLOWING JSON FORMAT:
            {{
                "observations": " ",
                "thoughts": " ",
                "next_actions": " ",
            }}
        """

    async def start_session_run(self, user_request):
        self.logger.log(f"Starting session run with user request: {user_request}")
        # try:
        #     subprocess.run(["tmux", "kill-server"], check=True)
        #     self.logger.log("Tmux server killed successfully.")
        # except subprocess.CalledProcessError as e:
        #     self.logger.log(f"Failed to kill tmux server: {e}", level="ERROR")

        # Check if the platform is Windows
    
        try:
            subprocess.run(["tmux", "kill-server"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to kill tmux server: {e}")


        self.working_memory.clear_memory()
        self.working_memory.add_or_update_module("OverarchingObjective", user_request)
        self.files_tool_instance.initialize_files()
        
        thread_id = self.working_memory.get_module("thread_id")
        if not thread_id:
            thread_id = self.agent.start_new_thread()
            self.working_memory.add_or_update_module("thread_id", thread_id)
        
        self.agent.generate_playground_access(thread_id)

        while True:
            run_id = self.agent.run_thread(thread_id, self.agent.assistant_id, additional_instructions=self.additional_instructions)
            await self.agent.check_run_status_and_execute_action(thread_id, run_id)
            self.agent.internal_monologue(thread_id, self.agent_internal_monologue_system_message)

    @staticmethod
    def schema() -> List[Dict[str, Any]]:
        """
        Returns the OpenAPI JSON schema for function calls.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": RunSessionTool.start_session_run.__name__,
                    "description": RunSessionTool.start_session_run.__doc__,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_request": {
                                "type": "string",
                                "description": "The user request to start the session with.",
                            }
                        },
                        "required": ["user_request"],
                    },
                },
            }
        ]

if __name__ == "__main__":
    run_session_tool = RunSessionTool()
    user_request = """ 

    Create a tool that will automatically draft email answers to all emails in the inbox with status unread.

EMAIL_ADDRESS = "ai@markokraemer.com"
EMAIL_PASSWORD = "10,-,piEsSA"
IMAP_SERVER = "mail.plutus.gmbh"
SMTP_SERVER = "mail.plutus.gmbh"
SMTP_PORT = 587
    """        
    asyncio.run(run_session_tool.start_session_run(user_request))

