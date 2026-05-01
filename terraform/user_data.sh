#!/bin/bash
set -euxo pipefail

# Update and install dependencies
dnf update -y
dnf install -y python3 python3-pip nginx unzip amazon-cloudwatch-agent

# Create Application Directory
mkdir -p /opt/luggage_portal
cd /opt/luggage_portal

# Download Code Artifact from S3
aws s3 cp s3://${artifact_bucket}/app.zip .
unzip -o app.zip

# Install Python Requirements
pip3 install -r requirements.txt gunicorn

# Auto-Hydrate Database securely using EC2 native IAM profiles
# Idempotent: only seeds if luggage_records table is empty (prevents crashes on ASG replacement launches)
python3 -c "
import seed, json, boto3
from botocore.exceptions import ClientError
try:
    import psycopg2
    creds = seed.get_db_credentials()
    conn = psycopg2.connect(host=creds['host'], port=creds['port'], database=creds['dbname'], user=creds['username'], password=creds['password'])
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM information_schema.tables WHERE table_name = %s', ('luggage_records',))
    table_exists = cur.fetchone()[0] > 0
    if table_exists:
        cur.execute('SELECT COUNT(*) FROM luggage_records')
        row_count = cur.fetchone()[0]
    else:
        row_count = 0
    cur.close()
    conn.close()
    if row_count == 0:
        print('Database empty — running seed...')
        seed.seed_db()
    else:
        print(f'Database already has {row_count} records — skipping seed.')
except Exception as e:
    print(f'Seed check failed, running seed as fallback: {e}')
    seed.seed_db()
"

# Setup Systemd Service for Gunicorn
cat > /etc/systemd/system/luggage.service << 'UNIT'
[Unit]
Description=Luggage Tracker Gunicorn Daemon
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/opt/luggage_portal
Environment="PATH=/usr/local/bin:/usr/bin"
ExecStart=/usr/local/bin/gunicorn -w 2 -b 127.0.0.1:8080 app:app
Restart=always

[Install]
WantedBy=multi-user.target
UNIT

# Reload and enable the backend service
systemctl daemon-reload
systemctl enable luggage.service
systemctl start luggage.service

# Configure Nginx Reverse Proxy
cat > /etc/nginx/conf.d/luggage.conf << 'NGINX'
server {
  listen 80;
  location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
}
NGINX

# Remove default nginx config to prevent port 80 conflicts if it exists
rm -f /etc/nginx/conf.d/default.conf

# Start Nginx
systemctl enable nginx
systemctl restart nginx

# ==========================================
# CloudWatch Agent: Stream Application Logs
# ==========================================
mkdir -p /opt/aws/amazon-cloudwatch-agent/etc

cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CWAGENT'
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "root"
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/nginx/access.log",
            "log_group_name": "/luggage-app/nginx/access",
            "log_stream_name": "{instance_id}",
            "retention_in_days": 7
          },
          {
            "file_path": "/var/log/nginx/error.log",
            "log_group_name": "/luggage-app/nginx/error",
            "log_stream_name": "{instance_id}",
            "retention_in_days": 7
          }
        ]
      }
    }
  }
}
CWAGENT

# Start CloudWatch Agent with the configuration file
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
  -s
