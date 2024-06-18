import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from llm import make_llm_api_call
import logging

EMAIL_ADDRESS = "ai@markokraemer.com"
EMAIL_PASSWORD = "10,-,piEsSA"
IMAP_SERVER = "mail.plutus.gmbh"
SMTP_SERVER = "mail.plutus.gmbh"
SMTP_PORT = 587

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def connect_to_email():
    try:
        logging.info("Connecting to email server...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select('inbox')
        logging.info("Connected to email server.")
        return mail
    except Exception as e:
        logging.error(f"Failed to connect to email server: {e}")
        raise


def fetch_unread_emails(mail):
    try:
        logging.info("Fetching unread emails...")
        status, response = mail.search(None, 'UNSEEN')
        email_ids = response[0].split()
        logging.info(f"Fetched {len(email_ids)} unread emails.")
        return email_ids
    except Exception as e:
        logging.error(f"Failed to fetch unread emails: {e}")
        raise


def fetch_email_details(mail, email_id):
    try:
        status, data = mail.fetch(email_id, '(RFC822)')
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        email_details = {
            'From': msg['From'],
            'Subject': msg['Subject'],
            'Body': ''
        }
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    email_details['Body'] = part.get_payload(decode=True).decode()
                    break
        else:
            email_details['Body'] = msg.get_payload(decode=True).decode()
        return email_details
    except Exception as e:
        logging.error(f"Failed to fetch email details: {e}")
        raise


def draft_reply(email_content):
    try:
        logging.info("Drafting reply...")
        messages = [
            {"role": "system", "content": "You are an AI assistant."},
            {"role": "user", "content": email_content}
        ]
        response = make_llm_api_call(messages, model_name='gpt-4o')
        reply_content = response['choices'][0]['message']['content']
        logging.info("Drafted reply.")
        return reply_content
    except Exception as e:
        logging.error(f"Failed to draft reply: {e}")
        raise


def send_email(reply_content, original_email):
    try:
        logging.info("Sending email...")
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = original_email['From']
        msg['Subject'] = "Re: " + original_email['Subject']
        msg.attach(MIMEText(reply_content, 'plain'))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, original_email['From'], msg.as_string())
        server.quit()
        logging.info("Email sent.")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        raise


def mark_as_read(mail, email_id):
    try:
        logging.info("Marking email as read...")
        mail.store(email_id, '+FLAGS', '\\Seen')
        logging.info("Email marked as read.")
    except Exception as e:
        logging.error(f"Failed to mark email as read: {e}")
        raise


def main():
    try:
        logging.info("Starting main process...")
        mail = connect_to_email()
        email_ids = fetch_unread_emails(mail)
        for email_id in email_ids:
            logging.info(f"Processing email ID: {email_id.decode()}")
            original_email = fetch_email_details(mail, email_id)
            logging.info(f"Fetched email details: From: {original_email['From']}, Subject: {original_email['Subject']}")
            reply_content = draft_reply(original_email['Body'])
            send_email(reply_content, original_email)
            mark_as_read(mail, email_id)
        mail.logout()
        logging.info("Main process completed.")
    except Exception as e:
        logging.error(f"An error occurred in the main process: {e}")


if __name__ == "__main__":
    main()
