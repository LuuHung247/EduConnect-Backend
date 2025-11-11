import os
import boto3


def create_topic(name):
    """Create an SNS topic and return its ARN. If boto3 not configured, return a fake ARN."""
    if boto3 and os.environ.get("AWS_REGION"):
        sns = boto3.client("sns")
        resp = sns.create_topic(Name=name)
        return resp.get("TopicArn")
    return f"arn:local:sns:{name}"


def delete_topic(arn):
    if boto3 and os.environ.get("AWS_REGION"):
        sns = boto3.client("sns")
        try:
            sns.delete_topic(TopicArn=arn)
        except Exception:
            pass
    return True


def subscribe_to_serie(topic_arn, email):
    if boto3 and os.environ.get("AWS_REGION"):
        sns = boto3.client("sns")
        return sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint=email)
    # fallback: pretend subscription succeeded
    return {"SubscriptionArn": f"arn:local:sub:{email}"}


def unsubscribe_from_topic(topic_arn, email):
    # In real impl we'd track subscription ARNs; here return a simple result
    return {"pendingConfirmation": False}


def publish_to_topic(topic_arn, subject, message):
    if boto3 and os.environ.get("AWS_REGION"):
        sns = boto3.client("sns")
        sns.publish(TopicArn=topic_arn, Subject=subject, Message=message)
        return True
    return True
