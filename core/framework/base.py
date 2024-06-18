import logging
import traceback
import uuid
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
import json
import sqlite3
from fastapi import FastAPI, HTTPException
import functools
from contextvars import ContextVar
from loguru import logger


# Database setup
conn = sqlite3.connect('../../logs.db', check_same_thread=False)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS logs (
    log_id TEXT,
    session_id TEXT,
    timestamp TEXT,
    level TEXT,
    message TEXT,
    unit_name TEXT,
    parent_id TEXT
)
''')
c.execute('''
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT,
    start_time TEXT
)
''')
conn.commit()

# Context for session management
session_context: ContextVar[str] = ContextVar('session_context', default=None)

@dataclass
class UnitResult:
    success: bool
    output: str

class DatabaseHandler:
    def __init__(self):
        self.conn = sqlite3.connect('../../logs.db', check_same_thread=False)
        self.cursor = self.conn.cursor()

    def insert_log(self, log_entry: Dict[str, Any]):
        self.cursor.execute('''
            INSERT INTO logs (log_id, session_id, timestamp, level, message, unit_name, parent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (log_entry['log_id'], log_entry['session_id'], log_entry['timestamp'], log_entry['level'],
              log_entry['message'], log_entry['unit_name'], log_entry['parent_id']))
        self.conn.commit()

    def insert_session(self, session_id: str):
        self.cursor.execute('''
            INSERT INTO sessions (session_id, start_time)
            VALUES (?, ?)
        ''', (session_id, datetime.now().isoformat()))
        self.conn.commit()

db_handler = DatabaseHandler()

class Logger:
    def __init__(self, unit_name: str):
        self.unit_name = unit_name
        self.session_id = session_context.get() or str(uuid.uuid4())
        if session_context.get() is None:
            session_context.set(self.session_id)
            db_handler.insert_session(self.session_id)  # Ensure the session is saved in the database

        self.call_stack = []
        self.logs = []
        logger.add(self.log_sink, level="DEBUG")

    def log_sink(self, message):
        log_entry = {
            "log_id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "level": message.record["level"].name,
            "message": message.record["message"],
            "unit_name": self.unit_name,
            "parent_id": self.call_stack[-1] if self.call_stack else None
        }
        self.logs.append(log_entry)
        db_handler.insert_log(log_entry)

    def log(self, message: str, level: str = "DEBUG"):
        logger.log(level, message)

    def log_exception(self, exception: Exception):
        self.log(f"Exception: {str(exception)}", "ERROR")
        self.log(traceback.format_exc(), "ERROR")

class Unit(ABC):
    def __init__(self):
        self.logger = Logger(self.__class__.__name__)

    @abstractmethod
    def schema(self) -> List[Dict[str, Any]]:
        pass

    def success_response(self, data: Dict[str, Any] | str) -> UnitResult:
        if isinstance(data, str):
            text = data
        else:
            text = json.dumps(data, indent=2)
        self.logger.log(f"Success response: {text}", "DEBUG")  
        return UnitResult(success=True, output=text)

    def fail_response(self, msg: str) -> UnitResult:
        self.logger.log(f"Failure response: {msg}", "ERROR")
        return UnitResult(success=False, output=msg)

    def log_method(self, method):
        @functools.wraps(method)
        def wrapper(*args, **kwargs):
            self.logger.call_stack.append(method.__name__)
            self.logger.log(f"Calling method: {method.__name__}", "DEBUG")
            try:
                result = method(*args, **kwargs)
                self.logger.log(f"Method {method.__name__} returned: {result}", "DEBUG")
                self.logger.call_stack.pop()
                return result
            except Exception as e:
                self.logger.log_exception(e)
                self.logger.call_stack.pop()
                raise
        return wrapper

    def __getattribute__(self, name):
        attr = super().__getattribute__(name)
        # Use super().__getattribute__ to avoid recursion
        if callable(attr) and name in super().__getattribute__('__class__').__dict__:
            return self.log_method(attr)
        return attr

# EXAMPLE
if __name__ == "__main__":
    import imaplib
    import email

    EMAIL_ADDRESS = "ai@markokraemer.com"
    EMAIL_PASSWORD = "10,-,piEsSA"
    IMAP_SERVER = "mail.plutus.gmbh"
    SMTP_SERVER = "mail.plutus.gmbh"
    SMTP_PORT = 587

    class EmailUnit(Unit):

        def __init__(self):
            super().__init__()

        def schema(self) -> List[Dict[str, Any]]:
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "read_emails",
                        "description": "Reads emails from the configured email account.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                }
            ]

        def read_emails(self) -> UnitResult:
            self.logger.log("Executing read_emails method", "DEBUG")
            try:
                mail = imaplib.IMAP4_SSL(IMAP_SERVER)
                mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                mail.select('inbox')

                status, messages = mail.search(None, 'ALL')
                email_ids = messages[0].split()[-3:]  # Get only the latest 3 emails
                emails = []

                for e_id in email_ids:
                    status, msg_data = mail.fetch(e_id, '(RFC822)')
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            body = msg.get_payload(decode=True)
                            emails.append({
                                "from": msg["from"],
                                "subject": msg["subject"],
                                "date": msg["date"],
                                "body": body.decode() if body else None
                            })

                mail.logout()
                return self.success_response(emails)
            except Exception as e:
                self.logger.log_exception(e)
                return self.fail_response(str(e))

    # Create an instance and call a method on the unit
    email_unit = EmailUnit()
    result = email_unit.read_emails()

    print(f"Result: {result}")
    print(f"Logs: {json.dumps(email_unit.logger.logs, indent=2)}")

app = FastAPI()

@app.get("/sessions")
async def get_sessions():
    c.execute('SELECT * FROM sessions')
    sessions = c.fetchall()
    return [{"session_id": session[0], "start_time": session[1]} for session in sessions]

@app.get("/sessions/{session_id}/logs")
async def get_session_logs(session_id: str):
    c.execute('SELECT * FROM logs WHERE session_id = ?', (session_id,))
    logs = c.fetchall()
    if not logs:
        raise HTTPException(status_code=404, detail="Session not found")
    return [{"log_id": log[0], "timestamp": log[2], "level": log[3], "message": log[4], "unit_name": log[5], "parent_id": log[6]} for log in logs]

@app.get("/sessions/{session_id}/logs/tree")
async def get_session_logs_tree(session_id: str):
    c.execute('SELECT * FROM logs WHERE session_id = ?', (session_id,))
    logs = c.fetchall()
    if not logs:
        raise HTTPException(status_code=404, detail="Session not found")

    log_dict = {log[0]: {"log_id": log[0], "timestamp": log[2], "level": log[3], "message": log[4], "unit_name": log[5], "parent_id": log[6], "children": []} for log in logs}

    root_logs = []

    for log in logs:
        log_id = log[0]
        parent_id = log[6]
        if parent_id and parent_id in log_dict:
            log_dict[parent_id]["children"].append(log_dict[log_id])
        else:
            root_logs.append(log_dict[log_id])

    return root_logs