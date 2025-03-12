from fastapi import FastAPI, Body
import os
from pydantic import BaseModel
import imaplib
import email
from email.header import decode_header
import requests
import ast
from upstash_workflow.fastapi import Serve
from upstash_workflow import AsyncWorkflowContext, CallResponse
from typing import TypedDict, Dict, List
from email.header import decode_header
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import fal_client


# Creating the app
app = FastAPI()
serve = Serve(app)

# Extracting the environment variables
IMAP_SERVER = os.getenv("IMAP_SERVER")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FAL_KEY = os.getenv("FAL_KEY")

# Reading the txt file 
with open("system_input.txt", "r") as file:
    content = file.read()


def fetch_emails():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    except Exception as e:
        return {"error": str(e)}

    try:
        mail.select("inbox")

        # Search for UNSEEN emails
        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()

        emails = []
        for email_id in email_ids:
            _, msg_data = mail.fetch(email_id, "(BODY[])")
            if not msg_data or not msg_data[0]:
                continue  # Skip if no data

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Mark email as read
            mail.store(email_id, "+FLAGS", "\\Seen")

            sender = msg.get("From")
            subject = decode_header(msg["Subject"])[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode(errors="ignore")

            text_content = ""
            images = []

            # Extract email content
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                # Extract text
                if content_type == "text/plain":
                    text_content += part.get_payload(decode=True).decode(errors="ignore") + "\n"
                elif content_type == "text/html" and not text_content:
                    text_content = part.get_payload(decode=True).decode(errors="ignore")

                # Extract images
                if "attachment" in content_disposition or content_type.startswith("image/"):
                    filename = part.get_filename()
                    if filename:
                        image_data = part.get_payload(decode=True)

                        # Getting the image url from fal.ai upload service
                        image_url = fal_client.upload(image_data, content_type, filename)
                        images.append({
                            "filename": filename,
                            "url": image_url
                        })

            emails.append({
                "sender": sender,
                "subject": subject,
                "text": text_content.strip(),
                "images": images
            })

        mail.close()
        mail.logout()
        return emails

    except Exception as e:
        return {"error": str(e)}  # Return error message


def send_email(sender, image_url, success):

    processed_image = None

    # Try to download image. In case of failure, just send the url itself.
    image_response = requests.get(image_url)
    if image_response.status_code == 200:
        processed_image = image_response.content

    # Create email
    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = sender

    if success:
        msg["Subject"] = "Your Images Are Processed!"

        if processed_image:
            body = "Thank you for choosing us. See attached for your processed image."
            msg.attach(MIMEText(body, "plain"))
            image_part = MIMEImage(processed_image, name="processed_image.png")
            msg.attach(image_part)
        else:
            body = f"Thank you for choosing us. See the link for your processed image: \n {image_url}"
            msg.attach(MIMEText(body, "plain"))
    
    else:
        msg["Subject"] = "About Your Image to be Processed"

        body = "Thank you for choosing us. We are sorry to say that there was an issue while processing your image."
        msg.attach(MIMEText(body, "plain"))

    # Send email
    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, sender, msg.as_string())



# Checking the environment variables
@app.get("/")
def read_root():

    key = os.getenv("DENEME_KEY")

    return {"key": key}


# Main Workflow 
@serve.post("/fal")
async def fal_wf(context: AsyncWorkflowContext):
    async def _fetch_emails() -> List:
        return fetch_emails()
    
    emails: List = await context.run("fetch-emails", _fetch_emails)

    if len(emails) != 0:
        mail = emails[0]
        mail_text = mail["text"]
        sender = mail["sender"]
        subject = mail["subject"]
        images = mail["images"]

        # Gather the subject and body
        whole_text = subject + "\n" + mail_text

        response1 = await context.call(
            "process-text",
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body={
                "model": "gpt-4-turbo",
                "messages": [
                    {"role": "system", "content": content},
                    {"role": "user", "content": whole_text}
                ],
                "temperature": 0.2
            },
            headers={
                "authorization": f"Bearer {OPENAI_API_KEY}",
            },
        )

        if 300 > response1.status >= 200:
            processed_text = response1.body["choices"][0]["message"]["content"]
            input_dict = ast.literal_eval(processed_text.replace("false", "False").replace("true", "True"))

        if len(images) != 0:
            url = images[0]["url"]
            filename = images[0]["filename"]

            input_dict["image_url"] = url

            response2 = await context.call(
                "process-image-fal",
                url = "https://queue.fal.run/fal-ai/clarity-upscaler",
                method = "POST",
                body = input_dict,
                headers = {
                    "authorization": f"Key {FAL_KEY}",
                    "Content-Type": "application/json",
                })
            
            if response2.status == 200:
                status_url = response2.body["status_url"]
                response_url = response2.body["response_url"]

                # Wait for 1 minute while the image is getting processed
                await context.sleep("wait-for-fal-response", "1m")

                response3 = await context.call(
                    "check-status",
                    url = status_url,
                    method = "GET",
                    headers={"Authorization": f"Key {FAL_KEY}"})
                
                if response3.status < 300 and response3.body["status"] == "COMPLETED":
                    response4 = await context.call(
                        "get-response",
                        url = response_url,
                        method = "GET",
                        headers={"Authorization": f"Key {FAL_KEY}"}
                    )

                    output_url = response4.body["image"]["url"]

                    async def _send_email():
                        return send_email(sender, output_url, True)

                    await context.run("send-email", _send_email)

    return "Workflow Done!"

