import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Automated Notification & Analytics Microservice.
    Reads securely off the protected SQS queue, parses the Ticket Service payload,
    determines SLA targets, and generates structured analytics logs for CloudWatch.
    """
    success_count = 0
    for record in event['Records']:
        try:
            # Safely extract payload: SQS natively wraps the underlying SNS payload
            sqs_payload = json.loads(record['body'])
            sns_message = json.loads(sqs_payload['Message'])

            bag_tag = sns_message.get('bag_tag', 'UNKNOWN_ASSET')
            issue = sns_message.get('issue_description', 'No details provided.')
            
            # Simulated urgency heuristic based on issue keywords
            urgency = "HIGH" if any(kw in issue.lower() for kw in ['lost', 'stolen', 'urgent', 'critical']) else "NORMAL"
            
            # Generate structured incident report
            incident_report = {
                "event_type": "TICKET_ESCALATION",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "asset_id": bag_tag,
                "urgency_level": urgency,
                "issue_summary": issue[:100] + ("..." if len(issue) > 100 else ""),
                "action_required": "Auto-assigned via Ticket Service"
            }

            # Emitting structured JSON to CloudWatch for advanced metric extraction
            logger.info(json.dumps(incident_report))
            logger.info(f"[{urgency}] Processed notification for asset {bag_tag}")
            success_count += 1

        except Exception as e:
            logger.error(json.dumps({"event_type": "PROCESSING_ERROR", "error": str(e)}))

    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully processed {success_count} notifications.')
    }
