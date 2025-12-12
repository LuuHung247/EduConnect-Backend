import boto3
import os
from botocore.exceptions import ClientError

def get_ses_client():
    return boto3.client(
        "ses",
        region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )

def send_email(recipient_emails: list, subject: str, body_text: str, body_html: str = None):
    """
    Gửi email thông qua AWS SES.
    """
    if not recipient_emails:
        print("Danh sách email rỗng, không gửi.")
        return None

    client = get_ses_client()
    sender_email = os.environ.get("AWS_SES_SENDER_EMAIL")
    
    if not sender_email:
        raise ValueError("Chưa cấu hình AWS_SES_SENDER_EMAIL")

    BATCH_SIZE = 50
    results = []

    try:
        for i in range(0, len(recipient_emails), BATCH_SIZE):
            batch_recipients = recipient_emails[i : i + BATCH_SIZE]
            
            response = client.send_email(
                Source=sender_email,
                Destination={
                    'ToAddresses': [sender_email],
                    'BccAddresses': batch_recipients
                },
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {
                        'Text': {'Data': body_text, 'Charset': 'UTF-8'},
                        'Html': {'Data': body_html or body_text, 'Charset': 'UTF-8'}
                    }
                }
            )
            results.append(response['MessageId'])
            print(f"Đã gửi batch email {i} -> {len(batch_recipients)} người.")

        return results

    except ClientError as e:
        print(f"Lỗi gửi email SES: {e.response['Error']['Message']}")
        raise e