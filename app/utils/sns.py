import os
import boto3
import logging

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get("AWS_REGION")


def get_sns_client():
    """Tạo SNS client với region"""
    if not AWS_REGION:
        logger.warning("⚠️ AWS_REGION not configured, using fallback mode")
        return None
    return boto3.client("sns", region_name=AWS_REGION)


def create_topic(name):
    """Create an SNS topic and return its ARN. If boto3 not configured, return a fake ARN."""
    try:
        sns = get_sns_client()
        if sns:
            resp = sns.create_topic(Name=name)
            arn = resp.get("TopicArn")
            logger.info(f"✅ Created SNS topic: {name} -> {arn}")
            return arn
    except Exception as e:
        logger.error(f"❌ Failed to create SNS topic: {e}")
    
    # Fallback for local development
    fake_arn = f"arn:local:sns:{name}"
    logger.warning(f"⚠️ Using fake ARN: {fake_arn}")
    return fake_arn


def delete_topic(arn):
    """Delete SNS topic"""
    try:
        sns = get_sns_client()
        if sns and not arn.startswith("arn:local"):
            sns.delete_topic(TopicArn=arn)
            logger.info(f"🗑️ Deleted SNS topic: {arn}")
    except Exception as e:
        logger.error(f"❌ Failed to delete topic: {e}")
    return True


def subscribe_to_serie(topic_arn, email):
    """Subscribe email to topic"""
    try:
        sns = get_sns_client()
        if sns and not topic_arn.startswith("arn:local"):
            response = sns.subscribe(
                TopicArn=topic_arn, 
                Protocol="email", 
                Endpoint=email
            )
            logger.info(f"📧 Subscribed {email} to {topic_arn}")
            return response
    except Exception as e:
        logger.error(f"❌ Failed to subscribe: {e}")
    
    # Fallback
    return {"SubscriptionArn": f"arn:local:sub:{email}"}


def unsubscribe_from_topic(topic_arn, email):
    """Unsubscribe email from topic"""
    try:
        sns = get_sns_client()
        if sns and not topic_arn.startswith("arn:local"):
            # List subscriptions và tìm subscription của email này
            response = sns.list_subscriptions_by_topic(TopicArn=topic_arn)
            subscriptions = response.get('Subscriptions', [])
            
            for sub in subscriptions:
                if sub['Endpoint'] == email:
                    if sub['SubscriptionArn'] == 'PendingConfirmation':
                        return {"pendingConfirmation": True}
                    
                    sns.unsubscribe(SubscriptionArn=sub['SubscriptionArn'])
                    logger.info(f"✅ Unsubscribed {email} from {topic_arn}")
                    return {"pendingConfirmation": False, "success": True}
            
            return {"pendingConfirmation": False, "success": False, "message": "Subscription not found"}
    except Exception as e:
        logger.error(f"❌ Failed to unsubscribe: {e}")
    
    return {"pendingConfirmation": False}


def publish_to_topic(topic_arn, subject, message):
    """Publish message to topic"""
    try:
        sns = get_sns_client()
        if sns and not topic_arn.startswith("arn:local"):
            sns.publish(
                TopicArn=topic_arn, 
                Subject=subject, 
                Message=message
            )
            logger.info(f"📤 Published to {topic_arn}: {subject}")
            return True
    except Exception as e:
        logger.error(f"❌ Failed to publish: {e}")
    
    return True